let currentMode = "week2";

const prompts = [
    "/overview system health",
    "/check all unhealthy devices",
    "/find critical devices",
    "/diagnose system issue",
    "/check devices with delayed heartbeat",
    "/show devices with alarms",
    "/review current IoT fleet status",
    "/summarize current fleet risk",
    "/prioritize devices needing attention"
];

function setMode(mode) {
    currentMode = mode;
}

function showTab(tabName, buttonElement) {
    const pages = document.querySelectorAll(".tab-page");

    pages.forEach(page => {
        page.classList.remove("active-page");
    });

    document.querySelectorAll(".top-tab").forEach(button => {
        button.classList.remove("active");
    });

    document.getElementById(tabName + "Tab").classList.add("active-page");

    if (buttonElement) {
        buttonElement.classList.add("active");
    }
}

function newChat() {
    document.getElementById("messageInput").value = "";
    document.getElementById("reasoningOutput").innerHTML = "No reasoning yet.";
    document.getElementById("responseOutput").textContent = "No diagnosis yet.";
}

function usePrompt(promptText) {
    const input = document.getElementById("messageInput");
    input.value = promptText;

    const homeButton = document.querySelector(".top-tab");
    showTab("home", homeButton);
}

function handleEnter(event) {
    if (event.key === "Enter") {
        sendMessage();
    }
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

    addHistoryItem(message);

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

                if (!latestStep) {
                    return;
                }

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

    const homeButton = document.querySelector(".top-tab");
    showTab("home", homeButton);

    sendMessage();
}

function addHistoryItem(message) {
    const history = document.getElementById("chatHistory");

    const item = document.createElement("div");
    item.className = "history-item";
    item.textContent = summarizeHistory(message);

    history.prepend(item);
}

function summarizeHistory(message) {
    const lowerMessage = message.toLowerCase();

    if (lowerMessage.includes("overview") || lowerMessage.includes("fleet")) {
        return "Reviewed fleet health";
    }

    if (lowerMessage.includes("unhealthy")) {
        return "Checked unhealthy devices";
    }

    if (lowerMessage.includes("critical")) {
        return "Found critical devices";
    }

    if (lowerMessage.includes("heartbeat")) {
        return "Checked heartbeat delays";
    }

    if (lowerMessage.includes("alarm")) {
        return "Reviewed active alarms";
    }

    if (lowerMessage.includes("diagnose")) {
        return "Ran device diagnosis";
    }

    return message.slice(0, 40);
}

async function refreshDevices() {
    try {
        const response = await fetch("/api/devices");
        const data = await response.json();

        const tableBody = document.getElementById("deviceTableBody");

        if (!tableBody) {
            return;
        }

        tableBody.innerHTML = "";

        data.devices.forEach(device => {
            tableBody.innerHTML += `
                <tr>
                    <td>${device.device_id}</td>
                    <td>
                        <span class="status-pill ${device.status}">
                            ${device.status}
                        </span>
                    </td>
                    <td>${device.cpu_usage}%</td>
                    <td>${device.memory_usage}%</td>
                    <td>${device.heartbeat_delay}s ago</td>
                    <td>
                        <button onclick="diagnoseDevice('${device.device_id}')">
                            Diagnose
                        </button>
                    </td>
                </tr>
            `;
        });

    } catch (error) {
        console.error("Failed to refresh devices:", error);
    }
}

setInterval(refreshDevices, 5000);