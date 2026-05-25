let currentMode = "week2";

const prompts = [
    "/diagnose gateway-003",
    "/diagnose sensor-001",
    "/diagnose sensor-002",
    "/status sensor-001",
    "/status sensor-002",
    "/logs gateway-003",
    "/alarms sensor-001"
];

function setMode(mode) {
    currentMode = mode;
}

function showTab(tabName) {
    const devicesTab = document.getElementById("devicesTab");
    const promptsTab = document.getElementById("promptsTab");
    const chatTab = document.getElementById("chatTab");

    devicesTab.classList.add("hidden");
    promptsTab.classList.add("hidden");
    chatTab.classList.add("hidden");

    document.querySelectorAll(".tab-button").forEach(button => {
        button.classList.remove("active");
    });

    if (tabName === "chat") {
        chatTab.classList.remove("hidden");
    }

    if (tabName === "devices") {
        devicesTab.classList.remove("hidden");
    }

    if (tabName === "prompts") {
        promptsTab.classList.remove("hidden");
    }

    event.target.classList.add("active");
}

function usePrompt(promptText) {
    const input = document.getElementById("messageInput");
    input.value = promptText;
    showTab("chat");
}

function handlePromptSuggestions() {
    const input = document.getElementById("messageInput");
    const suggestions = document.getElementById("promptSuggestions");

    const value = input.value.trim();

    if (!value.startsWith("/")) {
        suggestions.classList.add("hidden");
        suggestions.innerHTML = "";
        return;
    }

    const filtered = prompts.filter(prompt =>
        prompt.startsWith(value)
    );

    if (filtered.length === 0) {
        suggestions.classList.add("hidden");
        suggestions.innerHTML = "";
        return;
    }

    suggestions.innerHTML = filtered.map(prompt => {
        return `<div class="suggestion-item" onclick="usePrompt('${prompt}')">${prompt}</div>`;
    }).join("");

    suggestions.classList.remove("hidden");
}

async function sendMessage() {
    const input = document.getElementById("messageInput");
    const output = document.getElementById("responseOutput");
    const reasoningOutput = document.getElementById("reasoningOutput");
    const loading = document.getElementById("loading");
    const suggestions = document.getElementById("promptSuggestions");

    const message = input.value.trim();

    if (!message) {
        output.textContent = "Please enter a request.";
        return;
    }

    suggestions.classList.add("hidden");
    reasoningOutput.innerHTML = "No reasoning yet.";
    output.textContent = "";
    loading.classList.remove("hidden");

    if (currentMode === "week2") {
        await sendStreamMessage(message);
        loading.classList.add("hidden");
        return;
    }

    try {
        const response = await fetch("/api/diagnose", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message: message,
                mode: currentMode
            })
        });

        const data = await response.json();

        if (data.error) {
            output.textContent = "Error: " + data.error;
        } else {
            output.textContent = data.response;
        }

    } catch (error) {
        output.textContent = "Request failed: " + error;
    }

    loading.classList.add("hidden");
}

async function sendStreamMessage(message) {
    const output = document.getElementById("responseOutput");
    const reasoningOutput = document.getElementById("reasoningOutput");

    reasoningOutput.innerHTML = "";

    const response = await fetch("/api/diagnose-stream", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ message: message })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
        const { value, done } = await reader.read();

        if (done) break;

        const chunk = decoder.decode(value);
        const events = chunk.split("\n\n").filter(Boolean);

        events.forEach(eventText => {
            const jsonText = eventText.replace("data: ", "");
            const event = JSON.parse(jsonText);

            if (event.type === "thought") {
                reasoningOutput.innerHTML += `
                    <div class="reasoning-step">
                        <h4>Iteration ${event.iteration}</h4>

                        <p><strong>Thought:</strong><br>${event.thought}</p>
                        <p><strong>Action:</strong><br>${event.action}</p>
                    </div>
                `;
            }

            if (event.type === "observation") {
                const steps = document.querySelectorAll(".reasoning-step");
                const latestStep = steps[steps.length - 1];

                latestStep.innerHTML += `
                    <p><strong>Observation:</strong></p>
                    <pre>${JSON.stringify(event.observation.output, null, 2)}</pre>
                `;
            }

            if (event.type === "final") {
                output.textContent = event.final_answer;
            }

            if (event.type === "error") {
                output.textContent = "Error: " + event.error;
            }
        });
    }
}

function diagnoseDevice(deviceId) {
    const input = document.getElementById("messageInput");
    input.value = `/diagnose ${deviceId}`;
    showTab("chat");
    sendMessage();
}