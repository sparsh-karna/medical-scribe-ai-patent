const loginTab = document.getElementById("tab-login");
const signupTab = document.getElementById("tab-signup");
const loginForm = document.getElementById("login-form");
const signupForm = document.getElementById("signup-form");

function showLogin() {
  loginTab.classList.add("active"); signupTab.classList.remove("active");
  loginForm.hidden = false; signupForm.hidden = true;
}
function showSignup() {
  signupTab.classList.add("active"); loginTab.classList.remove("active");
  signupForm.hidden = false; loginForm.hidden = true;
}

const params = new URLSearchParams(location.search);
if (params.get("mode") === "signup") showSignup(); else showLogin();

loginTab.addEventListener("click", showLogin);
signupTab.addEventListener("click", showSignup);

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Something went wrong.");
  return data;
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("login-error");
  errorEl.hidden = true;
  try {
    await postJSON("/api/auth/login", {
      email: document.getElementById("login-email").value,
      password: document.getElementById("login-password").value,
    });
    location.href = "app.html";
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  }
});

signupForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("signup-error");
  errorEl.hidden = true;
  try {
    await postJSON("/api/auth/signup", {
      name: document.getElementById("signup-name").value,
      email: document.getElementById("signup-email").value,
      password: document.getElementById("signup-password").value,
    });
    location.href = "app.html";
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  }
});
