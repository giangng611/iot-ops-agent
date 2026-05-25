let currentMode = "week2";

async function sendMessage() {
    const input = document.getElementById("messageInput");
    const output = document.getElementById("responseOutput");
    const loading = document.getElementById("loading");

    const message = input.value.trim();

    if (currentMode === "week2") {
        await sendStreamMessage(message);
        return;
    }

    if (!message) {
        output.textContent = "Please enter a request.";
        return;
    }

    loading.classList.remove("hidden");
    output.textContent = "";

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
            renderReasoning(data.steps);
        }

    } catch (error) {
        output.textContent = "Request failed: " + error;
    }

    loading.classList.add("hidden");
}


function diagnoseDevice(deviceId) {
    const input = document.getElementById("messageInput");
    input.value = `diagnose ${deviceId}`;
    sendMessage();
}

function setMode(mode) {

    currentMode = mode;

    console.log("Current mode:", currentMode);

}

function renderReasoning(steps) {
    const reasoningOutput = document.getElementById("reasoningOutput");

    if (!steps || steps.length === 0) {
        reasoningOutput.innerHTML = "No reasoning trace available.";
        return;
    }

    let html = "";

    steps.forEach(step => {
        html += `
            <div class="reasoning-step">
                <h4>Iteration ${step.iteration}</h4>

                <p>
                    <strong>Thought:</strong><br>
                    ${step.thought}
                </p>

                <p>
                    <strong>Action:</strong><br>
                    ${step.action}
                </p>

                <p><strong>Observation:</strong></p>
                <pre>${JSON.stringify(step.output, null, 2)}</pre>
            </div>
        `;
    });

    reasoningOutput.innerHTML = html;
}

async function sendStreamMessage(message) {
    const output = document.getElementById("responseOutput");
    const reasoningOutput = document.getElementById("reasoningOutput");
    const loading = document.getElementById("loading");

    output.textContent = "";
    reasoningOutput.innerHTML = "";
    loading.classList.remove("hidden");

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
                reasoningOutput.innerHTML += `
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

    loading.classList.add("hidden");
}
