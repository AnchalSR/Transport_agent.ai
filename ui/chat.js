const form = document.getElementById("chat-form");
const input = document.getElementById("chat-input");
const messages = document.getElementById("messages");
const guidedBtn = document.getElementById("guided-btn");
const micBtn = document.getElementById("mic-btn");

let fromOptions = [];
let toOptions = [];
const guidedState = {
  active: false,
  step: "",
  from: "",
};

function appendMessage(text, sender) {
  const item = document.createElement("div");
  item.className = `message ${sender}`;
  item.textContent = text;
  messages.appendChild(item);
  messages.scrollTop = messages.scrollHeight;
  return item;
}

function appendOptionList(options, onSelect) {
  const wrapper = appendMessage("", "bot");
  const list = document.createElement("div");
  list.className = "option-list";

  options.forEach((option) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "option-chip";
    chip.textContent = option;
    chip.addEventListener("click", () => onSelect(option));
    list.appendChild(chip);
  });

  wrapper.appendChild(list);
}

async function postChat(message) {
  const res = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });

  if (!res.ok) {
    throw new Error("chat request failed");
  }

  return res.json();
}

async function ensureOptions() {
  if (fromOptions.length > 0 && toOptions.length > 0) {
    return;
  }

  const payload = await postChat("__OPTIONS__");
  fromOptions = Array.isArray(payload.from_options) ? payload.from_options : [];
  toOptions = Array.isArray(payload.to_options) ? payload.to_options : [];
}

async function sendMessage(text) {
  appendMessage(text, "user");

  try {
    const payload = await postChat(text);
    fromOptions = Array.isArray(payload.from_options) ? payload.from_options : fromOptions;
    toOptions = Array.isArray(payload.to_options) ? payload.to_options : toOptions;
    appendMessage(payload.reply || "No response.", "bot");
  } catch (error) {
    appendMessage("Network/server error. Please try again.", "bot");
  }
}

async function startGuidedFlow() {
  guidedState.active = true;
  guidedState.step = "from";
  guidedState.from = "";

  try {
    await ensureOptions();
  } catch (error) {
    appendMessage("Could not load route options right now.", "bot");
    guidedState.active = false;
    guidedState.step = "";
    return;
  }

  appendMessage("Where are you right now?", "bot");
  appendOptionList(fromOptions, async (selectedFrom) => {
    if (!guidedState.active || guidedState.step !== "from") {
      return;
    }

    guidedState.from = selectedFrom;
    guidedState.step = "to";
    appendMessage(selectedFrom, "user");
    appendMessage("Where do you want to go?", "bot");

    appendOptionList(toOptions, async (selectedTo) => {
      if (!guidedState.active || guidedState.step !== "to") {
        return;
      }

      appendMessage(selectedTo, "user");
      guidedState.active = false;
      guidedState.step = "";

      const query = `${guidedState.from} to ${selectedTo}`;
      try {
        const payload = await postChat(query);
        appendMessage(payload.reply || "No response.", "bot");
      } catch (error) {
        appendMessage("Network/server error. Please try again.", "bot");
      }
    });
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) {
    return;
  }

  input.value = "";
  await sendMessage(text);
  input.focus();
});

guidedBtn.addEventListener("click", async () => {
  await startGuidedFlow();
});

function setupVoiceInput() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    micBtn.disabled = true;
    micBtn.title = "Speech recognition not supported in this browser";
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.lang = "en-IN";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  let listening = false;

  recognition.onstart = () => {
    listening = true;
    micBtn.classList.add("listening");
    micBtn.textContent = "Stop";
  };

  recognition.onend = () => {
    listening = false;
    micBtn.classList.remove("listening");
    micBtn.textContent = "Mic";
  };

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    input.value = transcript;
    input.focus();
  };

  micBtn.addEventListener("click", () => {
    if (listening) {
      recognition.stop();
      return;
    }
    recognition.start();
  });
}

setupVoiceInput();
