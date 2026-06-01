function showSignup() {
    document.getElementById("loginPanel").classList.add("hidden");
    document.getElementById("signupPanel").classList.remove("hidden");
    document.getElementById("authMessage").textContent = "";

    document.getElementById("goLoginBtn").classList.add("hidden");
}

function showLogin() {
    document.getElementById("signupPanel").classList.add("hidden");
    document.getElementById("loginPanel").classList.remove("hidden");
    document.getElementById("authMessage").textContent = "";

    document.getElementById("goLoginBtn").classList.add("hidden");
}

function showForgotPassword() {
    document.getElementById("authMessage").textContent =
        "Account access is managed by the system administrator. Please contact the project owner.";
}

function togglePasswordVisibility(inputId, button) {
    const input = document.getElementById(inputId);
    const isHidden = input.type === "password";

    input.type = isHidden ? "text" : "password";
    button.setAttribute(
        "aria-label",
        isHidden ? "Hide password" : "Show password"
    );
}

async function login() {
    const username = document.getElementById("loginUsername").value.trim();
    const password = document.getElementById("loginPassword").value.trim();
    const message = document.getElementById("authMessage");

    const response = await fetch("/api/login", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            username: username,
            password: password
        })
    });

    const data = await response.json();

    if (data.error) {
        message.textContent = data.error;
        return;
    }

    window.location.href = "/";
}

async function register() {
    const username = document.getElementById("signupUsername").value.trim();
    const password = document.getElementById("signupPassword").value.trim();
    const accessCode = document.getElementById("accessCode").value.trim();
    const message = document.getElementById("authMessage");

    const response = await fetch("/api/register", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            username: username,
            password: password,
            access_code: accessCode
        })
    });

    const data = await response.json();

    if (data.error) {
        message.textContent = data.error;
        return;
    }

    message.textContent =
    "Account created successfully. Please continue to log in.";

    document.getElementById("goLoginBtn").classList.remove("hidden");
}
