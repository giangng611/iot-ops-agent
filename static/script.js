async function sendMessage() {
    const input = document.getElementById("messageInput");
    const output = document.getElementById("responseOutput");
    const loading = document.getElementById("loading");

    const message = input.value.trim();

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
            body: JSON.stringify({ message: message })
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


function diagnoseDevice(deviceId) {
    const input = document.getElementById("messageInput");
    input.value = `diagnose ${deviceId}`;
    sendMessage();
}