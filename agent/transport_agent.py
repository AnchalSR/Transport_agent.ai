import csv
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class RouteRow:
    route_id: str
    from_stop: str
    to_stop: str
    bus_number: str
    departure_time: str
    departure_minutes: int
    duration_minutes: int
    stops: List[str]


class TransportAgent:
    def __init__(self, csv_path: Optional[Path] = None) -> None:
        base_dir = Path(__file__).resolve().parents[1]
        self.csv_path = csv_path or (base_dir / "data" / "raw" / "bus_routes.csv")
        self.routes = self._load_csv()
        self.from_options = sorted({row.from_stop for row in self.routes})
        self.to_options = sorted({row.to_stop for row in self.routes})
        self.known_stops = self._build_stop_list()
        self.stop_lookup = {self._normalize(stop): stop for stop in self.known_stops}
        self.aliases = {
            "airport": "amausi airport",
            "amausi": "amausi airport",
            "station": "charbagh",
            "railway station": "charbagh",
            "charbagh station": "charbagh",
            "gomtinagar": "gomti nagar",
            "gomti nagr": "gomti nagar",
        }

    def get_options(self) -> Dict[str, List[str]]:
        return {
            "from_options": self.from_options,
            "to_options": self.to_options,
        }

    def find_route(self, from_stop: str, to_stop: str, after_time: str = "") -> Optional[Dict[str, object]]:
        resolved_from = self._resolve_stop(from_stop)
        resolved_to = self._resolve_stop(to_stop)
        if not resolved_from or not resolved_to:
            return None

        after_minutes = self._parse_time(after_time)
        matches: List[Tuple[Tuple[int, int, str], Dict[str, object]]] = []

        for route in self.routes:
            leg = self._route_leg(route.stops, resolved_from, resolved_to)
            if leg is None:
                continue

            start_idx, end_idx = leg
            if after_minutes is not None and route.departure_minutes < after_minutes:
                continue

            payload = {
                "bus_number": route.bus_number,
                "departure_time": route.departure_time,
                "duration_minutes": route.duration_minutes,
                "stops": route.stops[start_idx : end_idx + 1],
            }

            if after_minutes is not None:
                key = (
                    route.departure_minutes - after_minutes,
                    route.duration_minutes,
                    route.route_id,
                )
            else:
                key = (
                    route.duration_minutes,
                    route.departure_minutes,
                    route.route_id,
                )

            matches.append((key, payload))

        if not matches:
            return None

        matches.sort(key=lambda item: item[0])
        return matches[0][1]

    def suggest_alternative(self, from_stop: str, to_stop: str, after_time: str = "") -> Optional[Dict[str, object]]:
        resolved_from = self._resolve_stop(from_stop)
        resolved_to = self._resolve_stop(to_stop)
        if not resolved_from or not resolved_to:
            return None

        after_minutes = self._parse_time(after_time)
        first_legs: List[Dict[str, object]] = []
        second_legs_by_transfer: Dict[str, List[Dict[str, object]]] = {}

        for route in self.routes:
            start_idx = self._find_stop_index(route.stops, resolved_from)
            if start_idx is not None and (after_minutes is None or route.departure_minutes >= after_minutes):
                for transfer_idx in range(start_idx + 1, len(route.stops)):
                    transfer_stop = route.stops[transfer_idx]
                    leg_payload = {
                        "transfer_stop": transfer_stop,
                        "bus_number": route.bus_number,
                        "departure_time": route.departure_time,
                        "departure_minutes": route.departure_minutes,
                        "duration_minutes": self._segment_duration(route, start_idx, transfer_idx),
                        "stops": route.stops[start_idx : transfer_idx + 1],
                    }
                    first_legs.append(leg_payload)

            end_idx = self._find_stop_index(route.stops, resolved_to)
            if end_idx is not None:
                for transfer_idx in range(0, end_idx):
                    transfer_stop = route.stops[transfer_idx]
                    leg_payload = {
                        "transfer_stop": transfer_stop,
                        "bus_number": route.bus_number,
                        "departure_time": route.departure_time,
                        "departure_minutes": route.departure_minutes,
                        "duration_minutes": self._segment_duration(route, transfer_idx, end_idx),
                        "stops": route.stops[transfer_idx : end_idx + 1],
                    }

                    transfer_key = self._normalize(transfer_stop)
                    if transfer_key not in second_legs_by_transfer:
                        second_legs_by_transfer[transfer_key] = []
                    second_legs_by_transfer[transfer_key].append(leg_payload)

        best_plan: Optional[Tuple[Tuple[int, int, int, str], Dict[str, object]]] = None

        for leg1 in first_legs:
            transfer_key = self._normalize(str(leg1["transfer_stop"]))
            leg2_candidates = second_legs_by_transfer.get(transfer_key, [])
            if not leg2_candidates:
                continue

            leg2 = self._best_second_leg_for_first_leg(leg2_candidates, int(leg1["departure_minutes"]))

            if (
                self._normalize(str(leg1["stops"][0])) == self._normalize(str(leg2["stops"][0]))
                and self._normalize(str(leg1["stops"][-1])) == self._normalize(str(leg2["stops"][-1]))
            ):
                continue

            wait_minutes = max(0, int(leg2["departure_minutes"]) - int(leg1["departure_minutes"]))
            total_duration = int(leg1["duration_minutes"]) + int(leg2["duration_minutes"]) + wait_minutes
            sort_key = (
                total_duration,
                int(leg1["departure_minutes"]),
                int(leg2["departure_minutes"]),
                str(leg1["bus_number"]),
            )

            payload = {
                "type": "transfer",
                "from_stop": resolved_from,
                "to_stop": resolved_to,
                "transfer_stop": leg1["transfer_stop"],
                "leg1": {
                    "bus_number": leg1["bus_number"],
                    "departure_time": leg1["departure_time"],
                    "duration_minutes": leg1["duration_minutes"],
                    "stops": leg1["stops"],
                },
                "leg2": {
                    "bus_number": leg2["bus_number"],
                    "departure_time": leg2["departure_time"],
                    "duration_minutes": leg2["duration_minutes"],
                    "stops": leg2["stops"],
                },
                "total_duration_minutes": total_duration,
            }

            if best_plan is None or sort_key < best_plan[0]:
                best_plan = (sort_key, payload)

        return best_plan[1] if best_plan else None

    def _load_csv(self) -> List[RouteRow]:
        rows: List[RouteRow] = []
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                stops = [stop.strip() for stop in row["stops"].split("|") if stop.strip()]
                departure = row["departure_time"].strip()
                rows.append(
                    RouteRow(
                        route_id=row["route_id"].strip(),
                        from_stop=row["from_stop"].strip(),
                        to_stop=row["to_stop"].strip(),
                        bus_number=row["bus_number"].strip(),
                        departure_time=departure,
                        departure_minutes=self._clock_to_minutes(departure),
                        duration_minutes=int(row["duration_minutes"]),
                        stops=stops,
                    )
                )
        return rows

    def _build_stop_list(self) -> List[str]:
        ordered: List[str] = []
        seen = set()
        for route in self.routes:
            for stop in route.stops:
                key = self._normalize(stop)
                if key not in seen:
                    seen.add(key)
                    ordered.append(stop)
        return ordered

    def _resolve_stop(self, raw_stop: str) -> Optional[str]:
        key = self._normalize(raw_stop)
        if not key:
            return None

        key = self.aliases.get(key, key)
        if key in self.stop_lookup:
            return self.stop_lookup[key]

        best_name = None
        best_score = 0.0
        for stop in self.known_stops:
            stop_key = self._normalize(stop)
            score = SequenceMatcher(None, key, stop_key).ratio()
            if key in stop_key or stop_key in key:
                score += 0.12
            if score > best_score:
                best_score = score
                best_name = stop

        if best_name is None or best_score < 0.70:
            return None
        return best_name

    def _route_leg(self, stops: List[str], from_stop: str, to_stop: str) -> Optional[Tuple[int, int]]:
        normalized_stops = [self._normalize(stop) for stop in stops]
        from_key = self._normalize(from_stop)
        to_key = self._normalize(to_stop)

        try:
            start = normalized_stops.index(from_key)
        except ValueError:
            return None

        for end in range(start + 1, len(normalized_stops)):
            if normalized_stops[end] == to_key:
                return start, end
        return None

    def _find_stop_index(self, stops: List[str], stop_name: str) -> Optional[int]:
        target = self._normalize(stop_name)
        normalized = [self._normalize(item) for item in stops]
        try:
            return normalized.index(target)
        except ValueError:
            return None

    def _segment_duration(self, route: RouteRow, start_idx: int, end_idx: int) -> int:
        total_edges = max(1, len(route.stops) - 1)
        segment_edges = max(1, end_idx - start_idx)
        return max(5, round(route.duration_minutes * (segment_edges / total_edges)))

    def _best_second_leg_for_first_leg(self, candidates: List[Dict[str, object]], first_departure: int) -> Dict[str, object]:
        def key_fn(leg: Dict[str, object]) -> Tuple[int, int, str]:
            departure = int(leg["departure_minutes"])
            wait = departure - first_departure
            if wait < 0:
                wait += 24 * 60
            return (wait, int(leg["duration_minutes"]), str(leg["bus_number"]))

        return sorted(candidates, key=key_fn)[0]

    def _parse_time(self, value: str) -> Optional[int]:
        text = value.strip()
        if not text:
            return None
        try:
            return self._clock_to_minutes(text)
        except ValueError:
            return None

    def _normalize(self, value: str) -> str:
        return " ".join(value.strip().lower().split())

    def _clock_to_minutes(self, hhmm: str) -> int:
        parsed = datetime.strptime(hhmm, "%H:%M")
        return parsed.hour * 60 + parsed.minute
