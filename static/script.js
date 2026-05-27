const socket = io();

socket.on("connect", () => {
    console.log("Connected to realtime device stream.");
});

socket.on("device_update", (data) => {
    allDevices = data.devices;
    currentAlerts = data.alerts;

    renderDeviceTable();
    renderAlertCenter();
    renderCharts();
});

let currentMode = "week2";
let allDevices = [];
let chats = [];
let currentChatId = null;
let latestReasoningSteps = [];
let reasoningDrawerOpen = false;
let currentAlerts = {
    critical_count: 0,
    warning_count: 0
};
let healthChart = null;
let metricsChart = null;
let deviceHistoryChart = null;
let reasoningTypingQueue = Promise.resolve();
let pendingFinalAnswer = null;
let reasoningTypingActive = false;
let pendingDeleteChatId = null;
let isAgentRunning = false;

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
    if (isAgentRunning && tabName !== "home") {
        return;
    }

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

    if (tabName !== "home") {
        closeReasoningDrawer();
    }

    if (tabName !== "profile") {
        closeProfileDrawer();
    }
}

function newChat() {
    if (isAgentRunning) {
        return;
    }

    const homeButton = document.querySelector(".top-tab");
    showTab("home", homeButton);
    currentChatId = null;
    latestReasoningSteps = [];

    document.getElementById("messageInput").value = "";
    document.getElementById("chatMessages").innerHTML = "";

    const hero = document.getElementById("homeHero");
    hero.classList.remove("hidden");

    const suggestions = document.getElementById("promptSuggestions");
    suggestions.classList.add("hidden");
    suggestions.innerHTML = "";

    closeReasoningDrawer();
    renderChatHistory();
}

async function createChatIfNeeded(message) {
    if (currentChatId !== null) {
        return;
    }

    const response = await fetch("/api/chats", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            message: message
        })
    });

    const data = await response.json();

    currentChatId = data.chat_id;

    const chat = {
        id: currentChatId,
        title: data.title,
        isPinned: false,
        messages: []
    };

    chats.unshift(chat);
    renderChatHistory();
}

function usePrompt(promptText) {
    const input = document.getElementById("messageInput");
    const suggestions = document.getElementById("promptSuggestions");

    input.value = promptText;

    suggestions.classList.add("hidden");
    suggestions.innerHTML = "";

    const homeButton = document.querySelector(".top-tab");
    showTab("home", homeButton);

    input.focus();
}

function handleEnter(event) {
    if (event.key === "Enter") {
        if (isAgentRunning) {
            event.preventDefault();
            return;
        }

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
    if (isAgentRunning) {
        return;
    }

    isAgentRunning = true;
    latestReasoningSteps = [];
    const input = document.getElementById("messageInput");
    const loading = document.getElementById("loading");
    const suggestions = document.getElementById("promptSuggestions");
    const runButton = document.querySelector(".run-button");

    const message = input.value.trim();

    if (!message) {
        isAgentRunning = false;
        return;
    }

    input.value = "";
    input.disabled = true;
    setAppBusyState(true);

    await createChatIfNeeded(message);

    const hero = document.getElementById("homeHero");
    hero.classList.add("hidden");

    suggestions.classList.add("hidden");
        if (currentMode === "week2") {
        loading.innerHTML = `
            <span>Agent is thinking...</span>
            <button class="reasoning-loading-btn" onclick="openReasoningDrawer()">
                Show reasoning trace
            </button>
        `;
    } else {
        loading.innerHTML = `
            <span>Agent is thinking...</span>
        `;
    }

    loading.classList.remove("hidden");

    runButton.disabled = true;
    runButton.innerHTML = `
        Running...
        <span>Please wait</span>
    `;

    addUserMessage(message);

    await saveMessageToDatabase("user", message);

    try {
        let finalAnswer = "";

        if (currentMode === "week2") {
            finalAnswer = await sendStreamMessage(message);
        } else {
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
            finalAnswer = data.error ? "Error: " + data.error : data.response;
            latestReasoningSteps = [];
        }

        await addAssistantMessage(finalAnswer, latestReasoningSteps.length > 0);

        await saveMessageToDatabase(
            "assistant",
            finalAnswer,
            latestReasoningSteps
        );
        input.value = "";

    } catch (error) {
        addAssistantMessage("Request failed: " + error, false);

    } finally {
        loading.classList.add("hidden");

        runButton.disabled = false;
        runButton.innerHTML = `
            Run
            <span>Enter ↵</span>
        `;

        input.disabled = false;
        isAgentRunning = false;
        setAppBusyState(false);
    }
}

async function sendStreamMessage(message) {
    latestReasoningSteps = [];
    pendingFinalAnswer = null;
    reasoningTypingQueue = Promise.resolve();

    const response = await fetch("/api/diagnose-stream", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ message: message })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let finalAnswer = "";

    while (true) {
        const { value, done } = await reader.read();

        if (done) break;

        const chunk = decoder.decode(value);
        const events = chunk.split("\n\n").filter(Boolean);

        events.forEach(eventText => {
            const jsonText = eventText.replace("data: ", "");
            const event = JSON.parse(jsonText);

            if (event.type === "thought") {
                const step = {
                    iteration: event.iteration,
                    thought: event.thought,
                    action: event.action,
                    output: null
                };

                latestReasoningSteps.push(step);

                if (reasoningDrawerOpen) {
                    enqueueReasoningThoughtAction(step);
                }
            }

            if (event.type === "observation") {
                const latestStep = latestReasoningSteps[latestReasoningSteps.length - 1];

                if (latestStep) {
                    latestStep.output = event.observation.output;

                    if (reasoningDrawerOpen) {
                        enqueueReasoningObservation(latestStep);
                    }
                }
            }

            if (event.type === "final") {
                finalAnswer = event.final_answer;
                pendingFinalAnswer = finalAnswer;
            }

            if (event.type === "error") {
                finalAnswer = "Error: " + event.error;
                pendingFinalAnswer = finalAnswer;
            }
        });
    }

    await reasoningTypingQueue;

    return finalAnswer;
}

function diagnoseDevice(deviceId) {
    const input = document.getElementById("messageInput");
    input.value = `/diagnose ${deviceId}`;

    const homeButton = document.querySelector(".top-tab");
    showTab("home", homeButton);

    sendMessage();
}

function renderChatHistory() {
    const history = document.getElementById("chatHistory");
    history.innerHTML = "";
    const searchValue = document.getElementById("chatSearch")?.value.toLowerCase() || "";

    const visibleChats = chats.filter(chat =>
        chat.title.toLowerCase().includes(searchValue)
    );

    visibleChats.sort((a, b) => {
        if (a.isPinned === b.isPinned) {
            return b.id - a.id;
        }

        return a.isPinned ? -1 : 1;
    });

    visibleChats.forEach(chat => {
        const item = document.createElement("div");
        item.className = "history-item";

        if (chat.id === currentChatId) {
            item.classList.add("active");
        }

        item.innerHTML = `
            <span class="history-title">
                ${chat.isPinned ? `
                    <svg
                        class="pin-icon"
                        viewBox="0 0 24 24"
                        aria-hidden="true"
                    >
                        <path
                            d="M14 4L20 10L16 11L11 16L8 13L13 8L14 4Z"
                        ></path>

                        <path
                            d="M5 19L10 14"
                        ></path>
                    </svg>
                ` : ""}

                <span class="history-text">
                    ${chat.title}
                </span>
            </span>

            <button
                class="history-menu-btn"
                onclick="event.stopPropagation(); toggleHistoryMenu(${chat.id});"
            >
                ⋯
            </button>

            <div id="history-menu-${chat.id}" class="history-menu hidden">
                <button onclick="event.stopPropagation(); togglePinChat(${chat.id});">
                    ${chat.isPinned ? "Unpin" : "Pin"}
                </button>
                <button onclick="event.stopPropagation(); deleteChat(${chat.id});">
                    Delete
                </button>
            </div>
        `;

        item.onclick = function () {
            loadChat(chat.id);
        };

        history.appendChild(item);
    });
}

async function loadChat(chatId) {
    const homeButton = document.querySelector(".top-tab");
    showTab("home", homeButton);
    const chat = chats.find(item => item.id === chatId);

    if (!chat) {
        return;
    }

    currentChatId = chatId;

    const hero = document.getElementById("homeHero");
    hero.classList.add("hidden");

    const chatMessages = document.getElementById("chatMessages");
    chatMessages.innerHTML = "";

    const response = await fetch(`/api/chats/${chatId}/messages`);
    const data = await response.json();

    chat.messages = data.messages.map(message => ({
        role: message.role,
        content: message.content,
        createdAt: message.created_at,
        hasReasoning: Boolean(message.reasoning_steps),
        reasoningSteps: message.reasoning_steps
            ? JSON.parse(message.reasoning_steps)
            : []
    }));

    chat.messages.forEach(message => {
        if (message.role === "user") {
            renderUserMessage(message.content, message.createdAt);
        } else {
            renderAssistantMessage(
                message.content,
                message.hasReasoning,
                message.reasoningSteps || [],
                message.createdAt,
                false
            );
        }
    });

    renderChatHistory();
}

async function refreshDevices() {
    try {
        const response = await fetch("/api/devices");
        const data = await response.json();

        allDevices = data.devices;
        renderDeviceTable();

    } catch (error) {
        console.error("Failed to refresh devices:", error);
    }
}

function calculatePriority(device) {
    let score = 0;

    if (device.status === "critical") {
        score += 100;
    } else if (device.status === "warning") {
        score += 50;
    }

    score += Number(device.cpu_usage) || 0;
    score += Number(device.memory_usage) || 0;
    score += (Number(device.heartbeat_delay) || 0) / 10;

    return Math.round(score);
}

function renderDeviceTable() {
    const tableBody = document.getElementById("deviceTableBody");

    if (!tableBody) {
        return;
    }

    const searchValue = document.getElementById("deviceSearch")?.value.toLowerCase() || "";
    const statusValue = document.getElementById("statusFilter")?.value || "all";
    const sortValue = document.getElementById("sortSelect")?.value || "priority";

    let devices = [...allDevices];

    devices = devices.filter(device => {
        const matchesSearch = device.device_id.toLowerCase().includes(searchValue);
        const matchesStatus = statusValue === "all" || device.status === statusValue;

        return matchesSearch && matchesStatus;
    });

    devices.sort((a, b) => {
        if (sortValue === "priority") {
            return calculatePriority(b) - calculatePriority(a);
        }

        if (sortValue === "cpu") {
            return Number(b.cpu_usage) - Number(a.cpu_usage);
        }

        if (sortValue === "memory") {
            return Number(b.memory_usage) - Number(a.memory_usage);
        }

        if (sortValue === "heartbeat") {
            return Number(b.heartbeat_delay) - Number(a.heartbeat_delay);
        }

        if (sortValue === "timestamp") {
            return new Date(b.timestamp) - new Date(a.timestamp);
        }

        return 0;
    });

    tableBody.innerHTML = "";

    devices.forEach(device => {
        const priority = calculatePriority(device);

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
                <td>${priority}</td>
                <td>
                    <button onclick="diagnoseDevice('${device.device_id}')">
                        Diagnose
                    </button>
                </td>

                <td>
                    <button onclick="showDeviceHistory('${device.device_id}')">
                        History
                    </button>
                </td>
            </tr>
        `;
    });
}

function addUserMessage(message) {
    const chat = chats.find(item => item.id === currentChatId);

    if (chat) {
        chat.messages.push({
            role: "user",
            content: message
        });
    }

    renderUserMessage(message);
}

async function addAssistantMessage(message, hasReasoning) {
    const chat = chats.find(item => item.id === currentChatId);

    if (chat) {
        chat.messages.push({
            role: "assistant",
            content: message,
            hasReasoning: hasReasoning,
            reasoningSteps: [...latestReasoningSteps]
        });
    }

    await renderAssistantMessage(message, hasReasoning, latestReasoningSteps, null, true);
}

function renderUserMessage(message, timestamp = null) {
    const chatMessages = document.getElementById("chatMessages");

    chatMessages.innerHTML += `
        <div class="message-row user-row">
            <div class="message-stack">

                <div class="message-time user-time">
                    ${formatMessageTime(timestamp)}
                </div>

                <div class="message-bubble user-bubble">
                    ${message}
                </div>

            </div>
        </div>
    `;

    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function renderAssistantMessage(message, hasReasoning, reasoningSteps = [], timestamp = null, shouldType = false) {
    const chatMessages = document.getElementById("chatMessages");
    const reasoningId = `reasoning-${Date.now()}-${Math.random()}`;

    window[reasoningId] = reasoningSteps;

    chatMessages.innerHTML += `
        <div class="message-row assistant-row">
            <div class="message-stack">
                <div class="message-time assistant-time">
                    ${formatMessageTime(timestamp)}
                </div>

                <div class="message-bubble assistant-bubble">
                    ${hasReasoning ? `
                        <button class="reasoning-toggle" onclick="openReasoningDrawer('${reasoningId}')">
                            Show reasoning trace
                        </button>
                    ` : ""}

                    <pre class="typing-output">${shouldType ? "" : message}</pre>
                </div>
            </div>
        </div>
    `;

    const outputs = chatMessages.querySelectorAll(".typing-output");
    const latestOutput = outputs[outputs.length - 1];

    if (shouldType) {
        await typeTextIntoElementPromise(latestOutput, message, 8);
    }

    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function openReasoningDrawer(reasoningId = null) {
    const drawer = document.getElementById("reasoningDrawer");
    const mainArea = document.querySelector(".main-area");

    drawer.classList.remove("hidden");
    mainArea.classList.add("reasoning-open");
    reasoningDrawerOpen = true;

    if (reasoningId) {
        const steps = window[reasoningId] || [];
        renderReasoningStepsStatic(steps);
        return;
    }

    renderReasoningStepsStatic(latestReasoningSteps);

    latestReasoningSteps.forEach(step => {
        const stepElement = document.getElementById(`reasoning-step-${step.iteration}`);

        if (!stepElement) {
            createReasoningStepElement(step);
        }
    });
}

function closeReasoningDrawer() {
    const drawer = document.getElementById("reasoningDrawer");
    const mainArea = document.querySelector(".main-area");

    reasoningDrawerOpen = false;

    drawer.classList.add("hidden");
    mainArea.classList.remove("reasoning-open");
}

function renderReasoningDrawerLive() {
    return;
}

function renderReasoningStepsStatic(steps) {
    const content = document.getElementById("reasoningDrawerContent");

    if (!steps || steps.length === 0) {
        content.innerHTML = "No reasoning trace yet.";
        return;
    }

    let html = "";

    steps.forEach(step => {
        const outputText = step.output
            ? JSON.stringify(step.output, null, 2)
            : "Waiting for observation...";

        html += `
            <div class="reasoning-step" id="reasoning-step-${step.iteration}">
                <h4>Iteration ${step.iteration}</h4>

                <p>
                    <strong>Thought:</strong><br>
                    <span class="reasoning-thought">${step.thought || ""}</span>
                </p>

                <p>
                    <strong>Action:</strong><br>
                    <span class="reasoning-action">${step.action || ""}</span>
                </p>

                <p><strong>Observation:</strong></p>
                <pre class="reasoning-observation">${outputText}</pre>
            </div>
        `;
    });

    content.innerHTML = html;
}

function renderReasoningSteps(steps, shouldType = false) {
    const content = document.getElementById("reasoningDrawerContent");

    let html = "";

    steps.forEach((step, index) => {
        const outputText = step.output
            ? JSON.stringify(step.output, null, 2)
            : "Waiting for observation...";

        html += `
            <div class="reasoning-step" data-step-index="${index}">
                <h4>Iteration ${step.iteration}</h4>

                <p>
                    <strong>Thought:</strong><br>
                    <span class="reasoning-thought">${shouldType ? "" : step.thought}</span>
                </p>

                <p>
                    <strong>Action:</strong><br>
                    <span class="reasoning-action">${shouldType ? "" : step.action}</span>
                </p>

                <p><strong>Observation:</strong></p>
                <pre class="reasoning-observation">${shouldType ? "" : outputText}</pre>
            </div>
        `;
    });

    content.innerHTML = html || "No reasoning trace yet.";

    if (!shouldType) {
        return;
    }

    steps.forEach((step, index) => {
        const stepElement = content.querySelector(`[data-step-index="${index}"]`);

        if (!stepElement) {
            return;
        }

        const thoughtElement = stepElement.querySelector(".reasoning-thought");
        const actionElement = stepElement.querySelector(".reasoning-action");
        const observationElement = stepElement.querySelector(".reasoning-observation");

        const observationText = step.output
            ? JSON.stringify(step.output, null, 2)
            : "Waiting for observation...";

        typeReasoningStep(
            thoughtElement,
            step.thought,
            actionElement,
            step.action,
            observationElement,
            observationText
        );
    });
}

function createReasoningStepElement(step) {
    const content = document.getElementById("reasoningDrawerContent");

    if (content.textContent === "No reasoning trace yet.") {
        content.innerHTML = "";
    }

    const existing = document.getElementById(`reasoning-step-${step.iteration}`);

    if (existing) {
        return existing;
    }

    const wrapper = document.createElement("div");
    wrapper.className = "reasoning-step";
    wrapper.id = `reasoning-step-${step.iteration}`;

    wrapper.innerHTML = `
        <h4>Iteration ${step.iteration}</h4>

        <p>
            <strong>Thought:</strong><br>
            <span class="reasoning-thought"></span>
        </p>

        <p>
            <strong>Action:</strong><br>
            <span class="reasoning-action"></span>
        </p>

        <p><strong>Observation:</strong></p>
        <pre class="reasoning-observation"></pre>
    `;

    content.appendChild(wrapper);

    return wrapper;
}

function enqueueReasoningThoughtAction(step) {
    reasoningTypingQueue = reasoningTypingQueue.then(() => {
        const stepElement = createReasoningStepElement(step);

        const thoughtElement = stepElement.querySelector(".reasoning-thought");
        const actionElement = stepElement.querySelector(".reasoning-action");

        return typeTextIntoElementPromise(thoughtElement, step.thought, 4)
            .then(() => typeTextIntoElementPromise(actionElement, step.action, 4));
    });
}

function enqueueReasoningObservation(step) {
    reasoningTypingQueue = reasoningTypingQueue.then(() => {
        const stepElement = createReasoningStepElement(step);
        const observationElement = stepElement.querySelector(".reasoning-observation");

        const observationText = step.output
            ? JSON.stringify(step.output, null, 2)
            : "Waiting for observation...";

        return typeTextIntoElementPromise(observationElement, observationText, 1);
    });
}

function renderAlertCenter() {
    const badge = document.getElementById("alertBadge");
    const summary = document.getElementById("alertSummary");
    const alertList = document.getElementById("alertList");

    const critical = currentAlerts.critical_count || 0;
    const warning = currentAlerts.warning_count || 0;
    const total = critical + warning;

    if (total > 0) {
        badge.classList.remove("hidden");
        badge.textContent = total;
    } else {
        badge.classList.add("hidden");
    }

    if (!summary || !alertList) {
        return;
    }

    summary.innerHTML = `
        <div class="alert-summary-card critical-alert">
            <h2>${critical}</h2>
            <p>Critical</p>
        </div>

        <div class="alert-summary-card warning-alert">
            <h2>${warning}</h2>
            <p>Warning</p>
        </div>
    `;

    const alertDevices = allDevices.filter(device =>
        device.status === "critical" || device.status === "warning"
    );

    alertList.innerHTML = "";

    alertDevices.forEach(device => {
        alertList.innerHTML += `
            <div class="alert-item ${device.status}">
                <div>
                    <h3>${device.device_id}</h3>
                    <p>
                        Status: ${device.status} ·
                        CPU: ${device.cpu_usage}% ·
                        Memory: ${device.memory_usage}% ·
                        Heartbeat: ${device.heartbeat_delay}s
                    </p>
                </div>

                <div class="alert-actions">
                    <button onclick="diagnoseDevice('${device.device_id}')">
                        Diagnose
                    </button>

                    <button onclick="showDeviceHistory('${device.device_id}')">
                        History
                    </button>
                </div>
            </div>
        `;
    });
}

function toggleSidebar() {
    const appShell = document.querySelector(".app-shell");
    const toggle = document.getElementById("sidebarToggle");

    appShell.classList.toggle("sidebar-collapsed");

    if (appShell.classList.contains("sidebar-collapsed")) {
        toggle.innerHTML = "›";
    } else {
        toggle.innerHTML = "‹";
    }
}

function renderCharts() {
    if (!allDevices || allDevices.length === 0) {
        return;
    }

    renderHealthChart();
    renderMetricsChart();
}

function renderHealthChart() {
    const canvas = document.getElementById("healthChart");

    if (!canvas) {
        return;
    }

    const healthy = allDevices.filter(device => device.status === "healthy").length;
    const warning = allDevices.filter(device => device.status === "warning").length;
    const critical = allDevices.filter(device => device.status === "critical").length;

    const data = {
        labels: ["Healthy", "Warning", "Critical"],
        datasets: [
            {
                data: [healthy, warning, critical],
                backgroundColor: ["#22c55e", "#eab308", "#ef4444"],
                borderColor: "#171717",
                borderWidth: 2
            }
        ]
    };

    if (healthChart) {
        healthChart.data = data;
        healthChart.update();
        return;
    }

    healthChart = new Chart(canvas, {
        type: "doughnut",
        data: data,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: {
                        color: "#ececec"
                    }
                }
            }
        }
    });
}

function renderMetricsChart() {
    const canvas = document.getElementById("metricsChart");

    if (!canvas) {
        return;
    }

    const total = allDevices.length;

    const avgCpu = Math.round(
        allDevices.reduce((sum, device) => sum + Number(device.cpu_usage), 0) / total
    );

    const avgMemory = Math.round(
        allDevices.reduce((sum, device) => sum + Number(device.memory_usage), 0) / total
    );

    const avgHeartbeat = Math.round(
        allDevices.reduce((sum, device) => sum + Number(device.heartbeat_delay), 0) / total
    );

    const data = {
        labels: ["Avg CPU %", "Avg Memory %", "Avg Heartbeat Delay"],
        datasets: [
            {
                data: [avgCpu, avgMemory, avgHeartbeat],
                backgroundColor: ["#60a5fa", "#a78bfa", "#f97316"],
                borderRadius: 8,
                barPercentage: 0.75,
                categoryPercentage: 0.8
            }
        ]
    };

    if (metricsChart) {
        metricsChart.data = data;
        metricsChart.update();
        return;
    }

    metricsChart = new Chart(canvas, {
        type: "bar",
        data: data,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            layout: {
                padding: {
                    top: 8,
                    left: 8,
                    right: 8,
                    bottom: 0
                }
            },
            scales: {
                x: {
                    offset: true,
                    ticks: {
                        color: "#ececec"
                    },
                    grid: {
                        color: "#2f2f2f"
                    }
                },
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: "#ececec"
                    },
                    grid: {
                        color: "#2f2f2f"
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                }
            }
        }
    });
}

async function showDeviceHistory(deviceId) {
    const modal = document.getElementById("deviceHistoryModal");
    const title = document.getElementById("deviceHistoryTitle");

    title.textContent = `${deviceId} Telemetry History`;
    modal.classList.remove("hidden");

    const response = await fetch(`/api/telemetry/${deviceId}`);
    const data = await response.json();

    renderDeviceHistoryChart(data.history);
}

function closeDeviceHistory() {
    const modal = document.getElementById("deviceHistoryModal");
    modal.classList.add("hidden");
}

function renderDeviceHistoryChart(history) {
    const canvas = document.getElementById("deviceHistoryChart");

    if (!canvas) {
        return;
    }

    const labels = history.map(item => {
        const date = new Date(item.timestamp);
        return date.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit"
        });
    });

    const cpuData = history.map(item => item.cpu_usage);
    const memoryData = history.map(item => item.memory_usage);
    const heartbeatData = history.map(item => item.heartbeat_delay);

    const cpuWarningLine = history.map(() => 75);
    const memoryWarningLine = history.map(() => 80);
    const heartbeatWarningLine = history.map(() => 180);

    const data = {
        labels: labels,
        datasets: [
            {
                label: "CPU %",
                data: cpuData,
                borderColor: "#60a5fa",
                backgroundColor: "transparent",
                tension: 0.3,
                borderWidth: 3
            },
            {
                label: "Memory %",
                data: memoryData,
                borderColor: "#ec4899",
                backgroundColor: "transparent",
                tension: 0.3,
                borderWidth: 3,
                pointRadius: 2,
                pointHoverRadius: 5
            },
            {
                label: "Heartbeat Delay (s)",
                data: heartbeatData,
                borderColor: "#f97316",
                backgroundColor: "transparent",
                tension: 0.3,
                borderWidth: 3
            },
            {
                label: "CPU Warning Threshold",
                data: cpuWarningLine,
                borderColor: "#93c5fd",
                borderDash: [6, 6],
                pointRadius: 0,
                backgroundColor: "transparent"
            },
            {
                label: "Memory Warning Threshold",
                data: memoryWarningLine,
                borderColor: "#f9a8d4",
                borderDash: [6, 6],
                pointRadius: 0,
                backgroundColor: "transparent"
            },
            {
                label: "Heartbeat Warning Threshold",
                data: heartbeatWarningLine,
                borderColor: "#fdba74",
                borderDash: [6, 6],
                pointRadius: 0,
                backgroundColor: "transparent"
            }
        ]
    };

    if (deviceHistoryChart) {
        deviceHistoryChart.data = data;
        deviceHistoryChart.update();
        return;
    }

    deviceHistoryChart = new Chart(canvas, {
        type: "line",
        data: data,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: {
                mode: "index",
                intersect: false
            },
            scales: {
                x: {
                    ticks: {
                        color: "#ececec"
                    },
                    grid: {
                        color: "#2f2f2f"
                    }
                },
                y: {
                    ticks: {
                        color: "#ececec"
                    },
                    grid: {
                        color: "#2f2f2f"
                    }
                }
            },
            plugins: {
                legend: {
                    labels: {
                        color: "#ececec"
                    }
                }
            }
        }
    });
}

async function loadChatsFromDatabase() {
    const response = await fetch("/api/chats");
    const data = await response.json();

    chats = data.chats.map(chat => ({
        id: chat.id,
        title: chat.title,
        isPinned: chat.is_pinned,
        messages: []
    }));

    renderChatHistory();
}

document.addEventListener("DOMContentLoaded", () => {
    loadChatsFromDatabase();
});

async function saveMessageToDatabase(role, content, reasoningSteps = null) {
    if (currentChatId === null) {
        return;
    }

    await fetch(`/api/chats/${currentChatId}/messages`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            role: role,
            content: content,
            reasoning_steps: reasoningSteps
        })
    });
}

function toggleHistoryMenu(chatId) {
    document.querySelectorAll(".history-menu").forEach(menu => {
        if (menu.id !== `history-menu-${chatId}`) {
            menu.classList.add("hidden");
        }
    });

    const menu = document.getElementById(`history-menu-${chatId}`);
    menu.classList.toggle("hidden");
}

function deleteChat(chatId) {
    pendingDeleteChatId = chatId;
    document.getElementById("deleteChatModal").classList.remove("hidden");
}

function closeDeleteChatModal() {
    pendingDeleteChatId = null;
    document.getElementById("deleteChatModal").classList.add("hidden");
}

async function confirmDeleteChat() {
    if (pendingDeleteChatId === null) {
        return;
    }

    const chatId = pendingDeleteChatId;

    await fetch(`/api/chats/${chatId}`, {
        method: "DELETE"
    });

    chats = chats.filter(chat => chat.id !== chatId);

    if (currentChatId === chatId) {
        currentChatId = null;
        document.getElementById("chatMessages").innerHTML = "";
        document.getElementById("homeHero").classList.remove("hidden");
        closeReasoningDrawer();
    }

    closeDeleteChatModal();
    renderChatHistory();
}

function openLogoutModal() {
    document.getElementById("logoutModal").classList.remove("hidden");
}

function closeLogoutModal() {
    document.getElementById("logoutModal").classList.add("hidden");
}

function confirmLogout() {
    window.location.href = "/logout";
}

async function togglePinChat(chatId) {
    const response = await fetch(`/api/chats/${chatId}/pin`, {
        method: "POST"
    });

    const data = await response.json();

    const chat = chats.find(item => item.id === chatId);

    if (chat) {
        chat.isPinned = data.is_pinned;
    }

    renderChatHistory();
}

async function changePassword() {
    const currentPassword = document.getElementById("currentPassword").value;
    const newPassword = document.getElementById("newPassword").value;
    const message = document.getElementById("profileMessage");

    const response = await fetch("/api/profile/change-password", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            current_password: currentPassword,
            new_password: newPassword
        })
    });

    const data = await response.json();

    if (data.error) {
        message.textContent = data.error;
        return;
    }

    message.textContent = data.status;

    document.getElementById("currentPassword").value = "";
    document.getElementById("newPassword").value = "";
}

function openProfileDrawer(type) {
    const drawer = document.getElementById("profileDrawer");
    const title = document.getElementById("profileDrawerTitle");
    const subtitle = document.getElementById("profileDrawerSubtitle");
    const content = document.getElementById("profileDrawerContent");
    const profileTab = document.getElementById("profileTab");

    profileTab.classList.add("drawer-open");

    if (type === "security") {
        title.textContent = "Security";
        subtitle.textContent = "Update your account password.";

        content.innerHTML = `
            <div class="profile-form modal-form">
                <input id="currentPassword" type="password" placeholder="Current password">
                <input id="newPassword" type="password" placeholder="New password">

                <button onclick="changePassword()">Update Password</button>

                <p id="profileMessage"></p>
            </div>
        `;
    }

    if (type === "chats") {
        title.textContent = "Chat History";
        subtitle.textContent = "Manage saved conversations.";

        content.innerHTML = `
            <div class="drawer-info-list">
                <div>
                    <strong>Search chats</strong>
                    <p>Use the sidebar search box to quickly find previous conversations.</p>
                </div>

                <div>
                    <strong>Pin chats</strong>
                    <p>Hover over a chat, open the menu, and pin important conversations.</p>
                </div>

                <div>
                    <strong>Delete chats</strong>
                    <p>Use the chat menu to permanently delete a conversation from the database.</p>
                </div>
            </div>
        `;
    }

    if (type === "workspace") {
        title.textContent = "Workspace";
        subtitle.textContent = "Local workspace and storage details.";

        content.innerHTML = `
            <div class="drawer-info-list">
                <div>
                    <strong>Storage</strong>
                    <p>Telemetry, users, chats, messages, and reasoning traces are stored in SQLite.</p>
                </div>

                <div>
                    <strong>Realtime updates</strong>
                    <p>Device status, alerts, and charts update through WebSocket events.</p>
                </div>

                <div>
                    <strong>User isolation</strong>
                    <p>Each local account has its own saved chat history.</p>
                </div>
            </div>
        `;
    }

    if (type === "notifications") {
        title.textContent = "Notifications";
        subtitle.textContent = "Realtime warning and critical alert behavior.";

        content.innerHTML = `
            <div class="drawer-info-list">
                <div>
                    <strong>Alert Center</strong>
                    <p>Warning and critical device conditions appear in the Alerts tab.</p>
                </div>

                <div>
                    <strong>Alert badge</strong>
                    <p>The top navigation badge shows the number of active warning and critical devices.</p>
                </div>

                <div>
                    <strong>Operational thresholds</strong>
                    <p>CPU warning: 75%. Memory warning: 80%. Heartbeat warning: 180 seconds.</p>
                </div>
            </div>
        `;
    }

    drawer.classList.remove("hidden");
}

function closeProfileDrawer() {
    const drawer = document.getElementById("profileDrawer");
    const profileTab = document.getElementById("profileTab");

    if (drawer) {
        drawer.classList.add("hidden");
    }

    if (profileTab) {
        profileTab.classList.remove("drawer-open");
    }
}

function formatMessageTime(timestamp = null) {
    const date = timestamp ? new Date(timestamp) : new Date();

    return date.toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit"
    });
}

function typeTextIntoElement(element, text, speed = 8) {
    typeTextIntoElementPromise(element, text, speed);
}

function typeReasoningStep(thoughtElement, thoughtText, actionElement, actionText, observationElement, observationText) {
    typeTextIntoElement(thoughtElement, thoughtText, 4, () => {
        typeTextIntoElement(actionElement, actionText, 4, () => {
            typeTextIntoElement(observationElement, observationText, 2);
        });
    });
}

function typeTextIntoElementPromise(element, text, speed = 8) {
    return new Promise(resolve => {
        if (!element) {
            resolve();
            return;
        }

        element.textContent = "";
        element.classList.add("is-typing");

        let index = 0;

        function typeNextCharacter() {
            if (index < text.length) {
                element.textContent += text.charAt(index);
                index++;

                element.scrollIntoView({
                    behavior: "smooth",
                    block: "nearest"
                });

                setTimeout(typeNextCharacter, speed);
            } else {
                element.classList.remove("is-typing");
                resolve();
            }
        }

        typeNextCharacter();
    });
}

function setAppBusyState(isBusy) {
    document.querySelectorAll(".top-tab").forEach(button => {
        button.disabled = isBusy;
    });

    document.querySelectorAll(".history-item").forEach(item => {
        item.classList.toggle("disabled-item", isBusy);
    });

    const newChatButton = document.querySelector(".new-chat-btn");
    const logoutButton = document.querySelector(".logout-text-btn");
    const profileCard = document.querySelector(".profile-card");

    if (newChatButton) {
        newChatButton.disabled = isBusy;
    }

    if (logoutButton) {
        logoutButton.disabled = isBusy;
    }

    if (profileCard) {
        profileCard.classList.toggle("disabled-item", isBusy);
    }
}

//setInterval(refreshDevices, 5000);