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
let slashCommands = [];
let alertStates = {};
let promptsData = [];
let pendingDeletePromptId = null;
let pendingPasswordChange = null;

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
    const palette = document.getElementById("slashPalette");

    const value = input.value.trim();

    if (!value.startsWith("/")) {
        palette.classList.add("hidden");
        palette.innerHTML = "";
        return;
    }

    const filtered = slashCommands.filter(item =>
        item.command.toLowerCase().includes(value.toLowerCase()) ||
        item.title.toLowerCase().includes(value.toLowerCase()) ||
        item.category.toLowerCase().includes(value.toLowerCase())
    );

    if (filtered.length === 0) {
        palette.classList.add("hidden");
        palette.innerHTML = "";
        return;
    }

    palette.innerHTML = filtered.map(item => `
        <div class="slash-command" onclick="selectSlashCommand('${item.command}')">
            <div>
                <strong>${item.title}</strong>
                <p>${item.command}</p>
            </div>

            <span>${item.category}</span>
        </div>
    `).join("");

    palette.classList.remove("hidden");
}

function selectSlashCommand(command) {
    const input = document.getElementById("messageInput");
    const palette = document.getElementById("slashPalette");

    input.value = command;

    palette.classList.add("hidden");
    palette.innerHTML = "";

    input.focus();
}

async function loadSlashCommands() {
    const response = await fetch("/api/prompts");
    const data = await response.json();

    promptsData = data.prompts;
    slashCommands = data.prompts;

    renderPromptCards();
}

function renderPromptCards() {
    const grid = document.getElementById("promptGrid");
    const typeFilter =
    document.getElementById("promptTypeFilter")?.value || "all";

    if (!grid) {
        return;
    }

    const categoryFilter =
        document.getElementById("promptCategoryFilter")?.value || "all";

    const searchValue =
        document.getElementById("promptSearchInput")?.value.toLowerCase() || "";

    const filteredPrompts = promptsData.filter(prompt => {
        const matchesCategory =
            categoryFilter === "all" || prompt.category === categoryFilter;

        const matchesSearch =
            prompt.title.toLowerCase().includes(searchValue) ||
            prompt.command.toLowerCase().includes(searchValue) ||
            prompt.category.toLowerCase().includes(searchValue);

        const matchesType =
            typeFilter === "all" ||
            (typeFilter === "default" && prompt.is_default) ||
            (typeFilter === "custom" && !prompt.is_default);

        return matchesCategory && matchesSearch && matchesType;
    });

    grid.innerHTML = "";

    filteredPrompts.forEach(prompt => {
        grid.innerHTML += `
            <div class="prompt-card">
                <div class="prompt-card-top">
                    <span class="prompt-category">${prompt.category}</span>
                    ${prompt.is_default ? `<span class="prompt-default">Default</span>` : `<span class="prompt-custom">Custom</span>`}
                </div>

                <h3>${prompt.title}</h3>
                <p>${prompt.command}</p>

                <div class="prompt-card-actions">
                    <button onclick="usePrompt('${prompt.command}')">
                        Use
                    </button>

                    ${
                        prompt.is_default
                            ? `

                            `
                            : `
                                <button
                                    class="secondary-btn"
                                    onclick="openEditPromptModal(${prompt.id})"
                                >
                                    Edit
                                </button>

                                <button
                                    class="danger-btn"
                                    onclick="deleteCustomPrompt(${prompt.id})"
                                >
                                    Delete
                                </button>
                            `
                    }
                </div>
            </div>
        `;
    });
}

function openPromptModal() {
    editingPromptId = null;

    document.querySelector("#promptModal h2").textContent = "Create Prompt";
    document.getElementById("promptModal").classList.remove("hidden");
    document.getElementById("promptModalMessage").textContent = "";
}

function closePromptModal() {
    editingPromptId = null;
    document.querySelector("#promptModal h2").textContent = "Create Prompt";
    document.getElementById("promptModal").classList.add("hidden");

    document.getElementById("promptTitleInput").value = "";
    document.getElementById("promptCategoryInput").value = "";
    document.getElementById("promptCommandInput").value = "";
    document.getElementById("promptModalMessage").textContent = "";
}

let editingPromptId = null;

function openEditPromptModal(promptId) {
    const prompt = promptsData.find(item => item.id === promptId);

    if (!prompt) {
        return;
    }

    editingPromptId = promptId;

    document.querySelector("#promptModal h2").textContent = "Edit Prompt";
    document.getElementById("promptTitleInput").value = prompt.title;
    document.getElementById("promptCategoryInput").value = prompt.category;
    document.getElementById("promptCommandInput").value = prompt.command;
    document.getElementById("promptModalMessage").textContent = "";

    document.getElementById("promptModal").classList.remove("hidden");
}

async function createCustomPrompt() {
    const title = document.getElementById("promptTitleInput").value.trim();
    const category = document.getElementById("promptCategoryInput").value.trim() || "Custom";
    const command = document.getElementById("promptCommandInput").value.trim();
    const message = document.getElementById("promptModalMessage");

    if (!title || !command) {
        message.textContent = "Title and prompt command are required.";
        return;
    }

    const url = editingPromptId
        ? `/api/prompts/${editingPromptId}`
        : "/api/prompts";

    const method = editingPromptId ? "PUT" : "POST";

    const response = await fetch(url, {
        method: method,
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            title: title,
            category: category,
            command: command
        })
    });

    const data = await response.json();

    if (data.error) {
        message.textContent = data.error;
        return;
    }

    closePromptModal();
    await loadSlashCommands();
}

function deleteCustomPrompt(promptId) {
    pendingDeletePromptId = promptId;
    document.getElementById("deletePromptModal").classList.remove("hidden");
}

function closeDeletePromptModal() {
    pendingDeletePromptId = null;
    document.getElementById("deletePromptModal").classList.add("hidden");
}

async function confirmDeletePrompt() {
    if (pendingDeletePromptId === null) {
        return;
    }

    const promptId = pendingDeletePromptId;

    await fetch(`/api/prompts/${promptId}`, {
        method: "DELETE"
    });

    closeDeletePromptModal();
    await loadSlashCommands();
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
        let alertState = alertStates[device.device_id] || "active";

        const previousStatus = alertStates[device.device_id + "_status"];

        if (
            alertState === "resolved" &&
            previousStatus &&
            previousStatus !== device.status
        ) {
            alertState = "active";
            alertStates[device.device_id] = "active";
        }

        alertStates[device.device_id + "_status"] = device.status;

        const actionTime = alertStates[device.device_id + "_actionTime"];
        const actionTimeLabel = actionTime ? formatAlertActionTime(actionTime) : "";

        alertList.innerHTML += `
            <div class="alert-item ${device.status} ${alertState}">
                <div>
                    <h3>${device.device_id}</h3>
                    <p>
                        Status: ${device.status} ·
                        CPU: ${device.cpu_usage}% ·
                        Memory: ${device.memory_usage}% ·
                        Heartbeat: ${device.heartbeat_delay}s
                    </p>

                    <span class="alert-state-pill ${alertState}">
                        ${alertState}
                        ${actionTimeLabel ? `<span class="alert-state-time">${actionTimeLabel}</span>` : ""}
                    </span>
                </div>

                <div class="alert-actions">
                    <button onclick="diagnoseDevice('${device.device_id}')">
                        Diagnose
                    </button>

                    <button onclick="showDeviceHistory('${device.device_id}')">
                        History
                    </button>

                    ${alertState === "active" ? `
                        <button
                            class="secondary-btn"
                            onclick="acknowledgeAlert('${device.device_id}')"
                        >
                            Acknowledge
                        </button>
                    ` : ""}

                    ${alertState !== "resolved" ? `
                        <button
                            class="secondary-btn"
                            onclick="resolveAlert('${device.device_id}')"
                        >
                            Resolve
                        </button>
                    ` : ""}
                </div>
            </div>
        `;
    });
}

function acknowledgeAlert(deviceId) {
    alertStates[deviceId] = "acknowledged";
    alertStates[deviceId + "_actionTime"] = new Date().toISOString();

    renderAlertCenter();
}

function resolveAlert(deviceId) {
    alertStates[deviceId] = "resolved";
    alertStates[deviceId + "_actionTime"] = new Date().toISOString();

    renderAlertCenter();
}

function formatAlertActionTime(timestamp) {
    const date = new Date(timestamp);

    return date.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit"
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
    loadSlashCommands();
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

function changePassword() {
    const currentPassword = document.getElementById("currentPassword").value;
    const newPassword = document.getElementById("newPassword").value;
    const message = document.getElementById("profileMessage");

    if (!currentPassword || !newPassword) {
        message.textContent = "Both fields are required.";
        return;
    }

    pendingPasswordChange = {
        currentPassword: currentPassword,
        newPassword: newPassword
    };

    document.getElementById("changePasswordConfirmModal").classList.remove("hidden");
}

function closeChangePasswordConfirmModal() {
    pendingPasswordChange = null;
    document.getElementById("changePasswordConfirmModal").classList.add("hidden");
}

async function confirmChangePassword() {
    if (!pendingPasswordChange) {
        return;
    }

    const message = document.getElementById("profileMessage");

    const response = await fetch("/api/profile/change-password", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            current_password: pendingPasswordChange.currentPassword,
            new_password: pendingPasswordChange.newPassword
        })
    });

    const data = await response.json();

    if (data.error) {
        message.textContent = data.error;
        closeChangePasswordConfirmModal();
        return;
    }

    message.textContent = data.status;

    document.getElementById("currentPassword").value = "";
    document.getElementById("newPassword").value = "";

    closeChangePasswordConfirmModal();
}

function openProfileDrawer(type) {
    const drawer = document.getElementById("profileDrawer");
    const title = document.getElementById("profileDrawerTitle");
    const subtitle = document.getElementById("profileDrawerSubtitle");
    const content = document.getElementById("profileDrawerContent");
    const profileTab = document.getElementById("profileTab");

    profileTab.classList.add("drawer-open");

    if (type === "settings") {
        title.textContent = "Settings";
        subtitle.textContent =
            "Manage account preferences and workspace actions.";

        content.innerHTML = `
            <div class="drawer-info-list">

                <div>
                    <strong>Change password</strong>
                    <p>Update your account password securely.</p>

                    <button class="secondary-btn" onclick="togglePasswordPanel()">
                        Change Password
                    </button>

                    <div id="passwordPanel" class="profile-form hidden">
                        <input id="currentPassword" type="password" placeholder="Current password">
                        <input id="newPassword" type="password" placeholder="New password">

                        <div class="inline-form-actions">

                            <button onclick="changePassword()">
                                Update Password
                            </button>

                            <button
                                class="secondary-btn"
                                onclick="closePasswordPanel()"
                            >
                                Cancel
                            </button>

                        </div>

                        <p id="profileMessage"></p>
                    </div>
                </div>

                <div>
                    <strong>Change username</strong>
                    <p>Rename your local demo account.</p>

                    <button class="secondary-btn" onclick="toggleUsernamePanel()">
                        Change Username
                    </button>

                    <div id="usernamePanel" class="profile-form hidden">
                        <input id="newUsername" type="text" placeholder="New username">

                        <div class="inline-form-actions">

                            <button onclick="changeUsername()">
                                Update Username
                            </button>

                            <button
                                class="secondary-btn"
                                onclick="closeUsernamePanel()"
                            >
                                Cancel
                            </button>

                        </div>

                        <p id="usernameMessage"></p>
                    </div>
                </div>

                <div>
                    <strong>Log out</strong>
                    <p>End your current session and return to the login screen.</p>

                    <button class="secondary-btn" onclick="openLogoutModal()">
                        Log out
                    </button>
                </div>

                <div>
                    <strong>Delete account</strong>
                    <p>Permanently remove your account and saved workspace data.</p>

                    <button class="danger-btn" onclick="openDeleteAccountModal()">
                        Delete Account
                    </button>
                </div>

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
        title.textContent = "Session Activity";
        subtitle.textContent = "Runtime and workspace status for this session.";

        const selectedMode =
            document.getElementById("modeSelect")?.value || "week2";

        const modeLabel =
            selectedMode === "week2"
                ? "IOA v2 · Multi-step reasoning agent"
                : "IOA v1 · Single-step tool calling";

        const deviceCount =
            allDevices.length || 0;

        const hasRecentTelemetry =
            allDevices.some(device => {
                const timestamp =
                    new Date(device.timestamp).getTime();

                const now = Date.now();

                return (now - timestamp) < 90000;
            });

        const realtimeStatus =
            hasRecentTelemetry
                ? '<span class="status-online">Connected</span>'
                : '<span class="status-offline">Disconnected</span>';

        const environment =
            window.location.hostname.includes("localhost") ||
            window.location.hostname.includes("127.0.0.1")
                ? "Local development"
                : "Render deployment";

        content.innerHTML = `
            <div class="drawer-info-list">
                <div>
                    <strong>Current Agent Mode</strong>
                    <p>${modeLabel}</p>
                </div>

                <div>
                    <strong>Realtime Stream</strong>
                    <p>${realtimeStatus}</p>
                </div>

                <div>
                    <strong>Devices Monitored</strong>
                    <p>${deviceCount}</p>
                </div>

                <div>
                    <strong>Runtime Environment</strong>
                    <p>${environment}</p>
                </div>

                <div>
                    <strong>Storage Layer</strong>
                    <p>SQLite demo database for users, chats, messages, prompts, and telemetry.</p>
                </div>
            </div>
        `;
    }

    if (type === "notifications") {

        title.textContent = "Notifications";

        subtitle.textContent =
            "Realtime alert behavior and workspace notification preferences.";

        const alertBadgeEnabled =
            !document
                .getElementById("alertBadge")
                .classList.contains("hidden");

        const criticalEnabled = true;
        const warningEnabled = true;

        const refreshInterval =
            "30 seconds";

        content.innerHTML = `
            <div class="drawer-info-list">

                <div>
                    <strong>Critical Alerts</strong>

                    <p>
                        <span class="status-online">
                            Enabled
                        </span>
                    </p>
                </div>

                <div>
                    <strong>Warning Alerts</strong>

                    <p>
                        <span class="status-online">
                            Enabled
                        </span>
                    </p>
                </div>

                <div>
                    <strong>Alert Badge</strong>

                    <p>
                        ${
                            alertBadgeEnabled
                                ? '<span class="status-online">Visible</span>'
                                : '<span class="status-offline">Hidden</span>'
                        }
                    </p>
                </div>

                <div>
                    <strong>Telemetry Refresh Interval</strong>

                    <p>${refreshInterval}</p>
                </div>

                <div>
                    <strong>Notification Environment</strong>

                    <p>
                        Browser-based realtime alert monitoring
                        powered by Flask-SocketIO.
                    </p>
                </div>

            </div>
        `;
    }

    if (type === "usage") {
        title.textContent = "Usage Statistics";
        subtitle.textContent = "Account-level activity across your workspace.";

        content.innerHTML = `
            <div class="drawer-info-list">
                <div>
                    <strong>Loading usage statistics...</strong>
                    <p>Please wait.</p>
                </div>
            </div>
        `;

        loadUsageStats(content);
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

function openChangeUsernamePanel() {
    const message = document.getElementById("profileMessage");
    const mainProfileName = document.querySelector(".profile-name-main");

    if (mainProfileName) {
        mainProfileName.textContent = data.username;
    }

    if (message) {
        message.textContent = "Username change will be added in the next step.";
    }
}

function openDeleteAccountModal() {
    document.getElementById("deleteAccountModal").classList.remove("hidden");
    document.getElementById("deleteAccountMessage").textContent = "";
    document.getElementById("deleteAccountPassword").value = "";
}

function closeDeleteAccountModal() {
    document.getElementById("deleteAccountModal").classList.add("hidden");
}

async function confirmDeleteAccount() {
    const password = document.getElementById("deleteAccountPassword").value;
    const message = document.getElementById("deleteAccountMessage");

    if (!password) {
        message.textContent = "Password is required.";
        return;
    }

    const response = await fetch("/api/profile/delete-account", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            password: password
        })
    });

    const data = await response.json();

    if (data.error) {
        message.textContent = data.error;
        return;
    }

    window.location.href = "/login";
}

function togglePasswordPanel() {

    const panel =
        document.getElementById("passwordPanel");

    const usernamePanel =
        document.getElementById("usernamePanel");

    usernamePanel.classList.add("hidden");

    panel.classList.toggle("hidden");
}
function toggleUsernamePanel() {

    const panel =
        document.getElementById("usernamePanel");

    const passwordPanel =
        document.getElementById("passwordPanel");

    passwordPanel.classList.add("hidden");

    panel.classList.toggle("hidden");
}

async function changeUsername() {
    const newUsername = document.getElementById("newUsername").value.trim();
    const message = document.getElementById("usernameMessage");

    if (!newUsername) {
        message.textContent = "New username is required.";
        return;
    }

    const response = await fetch("/api/profile/change-username", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            new_username: newUsername
        })
    });

    const data = await response.json();

    if (data.error) {
        message.textContent = data.error;
        return;
    }

    message.textContent = data.status;

    document.querySelectorAll(".profile-name").forEach(element => {
        element.textContent = data.username;
    });

    const mainUsername =
        document.getElementById("profileMainUsername");

    if (mainUsername) {
        mainUsername.textContent = data.username;
    }

    document.getElementById("newUsername").value = "";
}

function closePasswordPanel() {

    const panel =
        document.getElementById("passwordPanel");

    panel.classList.add("hidden");

    document.getElementById("currentPassword").value = "";
    document.getElementById("newPassword").value = "";

    const message =
        document.getElementById("profileMessage");

    if (message) {
        message.textContent = "";
    }
}

function closeUsernamePanel() {

    const panel =
        document.getElementById("usernamePanel");

    panel.classList.add("hidden");

    document.getElementById("newUsername").value = "";

    const message =
        document.getElementById("usernameMessage");

    if (message) {
        message.textContent = "";
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

function openProfileFromSidebar() {
    if (isAgentRunning) {
        return;
    }

    const profileButton = document.querySelector(
        '.top-tab[onclick*="profile"]'
    );

    showTab("profile", profileButton);
}

async function loadUsageStats(content) {
    const response = await fetch("/api/profile/usage-stats");
    const data = await response.json();

    if (data.error) {
        content.innerHTML = `
            <div class="drawer-info-list">
                <div>
                    <strong>Error</strong>
                    <p>${data.error}</p>
                </div>
            </div>
        `;
        return;
    }

    content.innerHTML = `
        <div class="drawer-info-list">
            <div>
                <strong>Saved Conversations</strong>
                <p>${data.chat_count}</p>
            </div>

            <div>
                <strong>Messages Saved</strong>
                <p>${data.message_count}</p>
            </div>

            <div>
                <strong>Custom Prompts</strong>
                <p>${data.custom_prompt_count}</p>
            </div>

            <div>
                <strong>Devices Monitored</strong>
                <p>${data.device_count}</p>
            </div>
        </div>
    `;
}