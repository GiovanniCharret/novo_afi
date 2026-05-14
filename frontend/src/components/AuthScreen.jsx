import { useEffect, useState } from "react";

/**
 * F1 Fase C — Tela de autenticação com state machine interna.
 *
 * Views possíveis (em `view.name`):
 *   - "login"          — email + senha
 *   - "register"       — cria conta nova
 *   - "confirm-needed" — pós-registro, instrui o usuário a checar o e-mail
 *   - "confirm-result" — chega via URL ?confirm=TOKEN; auto-confirma e mostra resultado
 *   - "forgot"         — solicita link de redefinição
 *   - "reset"          — chega via URL ?reset=TOKEN; define nova senha
 *
 * Roteamento: lê `window.location.search` no mount. Após resolver,
 * limpa os params da URL via `history.replaceState` para não disparar
 * a mesma ação se o usuário recarregar.
 */

const MIN_PASSWORD_LENGTH = 10;

// F1 — hint mostrado só quando a SPA está rodando em localhost (dev local).
// O backend cria automaticamente o usuário dev@local / password em APP_ENV=development
// (ver backend/app/seeds/seed_dev_user.py).
const IS_LOCAL_DEV =
  typeof window !== "undefined" &&
  (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1");

function getInitialView() {
  if (typeof window === "undefined") return { name: "login", token: null };
  const params = new URLSearchParams(window.location.search);
  const confirm = params.get("confirm");
  if (confirm) return { name: "confirm-result", token: confirm };
  const reset = params.get("reset");
  if (reset) return { name: "reset", token: reset };
  return { name: "login", token: null };
}

function clearUrlParams() {
  if (typeof window === "undefined") return;
  window.history.replaceState({}, "", window.location.pathname);
}

async function postJson(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
  let payload = null;
  try { payload = await r.json(); } catch { /* sem corpo */ }
  return { ok: r.ok, status: r.status, payload };
}

export default function AuthScreen({ onLoggedIn }) {
  const [view, setView] = useState(getInitialView);
  // Email "lembrado" entre telas (login → forgot → reset, ou register → confirm-needed)
  const [rememberedEmail, setRememberedEmail] = useState("");

  const goto = (name, extras = {}) => {
    clearUrlParams();
    setView({ name, token: null, ...extras });
  };

  return (
    <div className="auth-shell">
      <div className="auth-card">
        {view.name === "login" && (
          <LoginPanel
            initialEmail={rememberedEmail}
            onSubmitEmail={setRememberedEmail}
            onLoggedIn={onLoggedIn}
            onForgot={() => goto("forgot")}
            onRegister={() => goto("register")}
          />
        )}

        {view.name === "register" && (
          <RegisterPanel
            initialEmail={rememberedEmail}
            onSubmitEmail={setRememberedEmail}
            onRegistered={(email) => {
              setRememberedEmail(email);
              goto("confirm-needed");
            }}
            onBackToLogin={() => goto("login")}
          />
        )}

        {view.name === "confirm-needed" && (
          <ConfirmNeededPanel
            email={rememberedEmail}
            onBackToLogin={() => goto("login")}
          />
        )}

        {view.name === "confirm-result" && (
          <ConfirmResultPanel
            token={view.token}
            onContinue={() => goto("login")}
          />
        )}

        {view.name === "forgot" && (
          <ForgotPanel
            initialEmail={rememberedEmail}
            onSubmitEmail={setRememberedEmail}
            onSent={() => goto("forgot-sent")}
            onBackToLogin={() => goto("login")}
          />
        )}

        {view.name === "forgot-sent" && (
          <ForgotSentPanel
            email={rememberedEmail}
            onBackToLogin={() => goto("login")}
          />
        )}

        {view.name === "reset" && (
          <ResetPanel
            token={view.token}
            onResetDone={() => goto("login")}
          />
        )}
      </div>
    </div>
  );
}

/* ───────────────────────────────────── LOGIN */

function LoginPanel({ initialEmail, onSubmitEmail, onLoggedIn, onForgot, onRegister }) {
  const [email, setEmail] = useState(initialEmail);
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    onSubmitEmail(email);
    const r = await postJson("/api/auth/login", { email, password });
    setSubmitting(false);
    if (!r.ok) {
      if (r.status === 403) {
        setError("Confirme seu e-mail antes de entrar. Cheque sua caixa de entrada.");
      } else {
        setError(r.payload?.detail ?? "E-mail ou senha incorretos.");
      }
      return;
    }
    onLoggedIn(r.payload?.user);
  }

  return (
    <>
      <p className="eyebrow">GFIP</p>
      <h1 className="auth-title">Entrar</h1>
      <p className="auth-subtitle">Acesso ao sistema de recebimento de notas fiscais.</p>
      <form className="login-form" onSubmit={handleSubmit}>
        <label className="field">
          <span className="field-label">E-mail</span>
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label className="field">
          <span className="field-label">Senha</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? "Entrando…" : "Entrar"}
        </button>
      </form>
      {error && <p className="auth-error">{error}</p>}
      <div className="auth-links">
        <button type="button" className="auth-link" onClick={onForgot}>
          Esqueci minha senha
        </button>
        <button type="button" className="auth-link" onClick={onRegister}>
          Não tem conta? Criar agora
        </button>
      </div>
      {IS_LOCAL_DEV && (
        <div className="auth-hint">
          Dev local: <code>dev@local</code> &nbsp;·&nbsp; <code>password</code>
        </div>
      )}
    </>
  );
}

/* ───────────────────────────────────── REGISTER */

function RegisterPanel({ initialEmail, onSubmitEmail, onRegistered, onBackToLogin }) {
  const [email, setEmail] = useState(initialEmail);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Senha precisa ter pelo menos ${MIN_PASSWORD_LENGTH} caracteres.`);
      return;
    }
    if (password !== confirmPassword) {
      setError("As senhas não coincidem.");
      return;
    }
    setSubmitting(true);
    onSubmitEmail(email);
    const r = await postJson("/api/auth/register", { email, password });
    setSubmitting(false);
    if (!r.ok) {
      if (r.status === 409) setError("Este e-mail já está cadastrado.");
      else setError(r.payload?.detail ?? "Não foi possível criar a conta.");
      return;
    }
    onRegistered(email);
  }

  return (
    <>
      <p className="eyebrow">GFIP</p>
      <h1 className="auth-title">Criar conta</h1>
      <p className="auth-subtitle">Cadastre-se com seu e-mail institucional.</p>
      <form className="login-form" onSubmit={handleSubmit}>
        <label className="field">
          <span className="field-label">E-mail</span>
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label className="field">
          <span className="field-label">Senha (mínimo {MIN_PASSWORD_LENGTH} caracteres)</span>
          <input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={MIN_PASSWORD_LENGTH}
          />
        </label>
        <label className="field">
          <span className="field-label">Confirmar senha</span>
          <input
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
          />
        </label>
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? "Criando…" : "Criar conta"}
        </button>
      </form>
      {error && <p className="auth-error">{error}</p>}
      <div className="auth-links">
        <button type="button" className="auth-link" onClick={onBackToLogin}>
          Já tem conta? Entrar
        </button>
      </div>
    </>
  );
}

/* ───────────────────────────────────── CONFIRM NEEDED (pós-registro) */

function ConfirmNeededPanel({ email, onBackToLogin }) {
  const [resendStatus, setResendStatus] = useState("idle"); // "idle" | "sending" | "sent"

  async function handleResend() {
    setResendStatus("sending");
    await postJson("/api/auth/resend-confirmation", { email });
    setResendStatus("sent");
  }

  return (
    <>
      <p className="eyebrow">GFIP</p>
      <h1 className="auth-title">Verifique seu e-mail</h1>
      <p className="auth-subtitle">
        Enviamos um link de confirmação para <strong>{email}</strong>. Clique no link
        em até 24 horas para ativar sua conta.
      </p>
      <div className="auth-info">
        Não recebeu? Cheque a pasta de spam ou peça reenvio abaixo.
      </div>
      <button
        type="button"
        className="btn-secondary"
        onClick={handleResend}
        disabled={resendStatus !== "idle"}
      >
        {resendStatus === "sending" && "Reenviando…"}
        {resendStatus === "sent" && "Enviado ✓"}
        {resendStatus === "idle" && "Reenviar e-mail"}
      </button>
      <div className="auth-links">
        <button type="button" className="auth-link" onClick={onBackToLogin}>
          Voltar ao login
        </button>
      </div>
    </>
  );
}

/* ───────────────────────────────────── CONFIRM RESULT (?confirm=TOKEN) */

function ConfirmResultPanel({ token, onContinue }) {
  const [status, setStatus] = useState("loading"); // "loading" | "success" | "error"
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const r = await fetch(
          `/api/auth/confirm?token=${encodeURIComponent(token)}`,
          { credentials: "same-origin" }
        );
        if (!active) return;
        if (r.ok) {
          setStatus("success");
        } else {
          const payload = await r.json().catch(() => ({}));
          setErrorMsg(payload.detail ?? "Não foi possível confirmar o e-mail.");
          setStatus("error");
        }
      } catch (e) {
        if (active) {
          setErrorMsg(e.message);
          setStatus("error");
        }
      }
    })();
    return () => { active = false; };
  }, [token]);

  return (
    <>
      <p className="eyebrow">GFIP</p>
      {status === "loading" && (
        <>
          <h1 className="auth-title">Confirmando…</h1>
          <p className="auth-subtitle">Validando seu token de e-mail.</p>
        </>
      )}
      {status === "success" && (
        <>
          <h1 className="auth-title">E-mail confirmado</h1>
          <p className="auth-subtitle">Sua conta está ativa. Faça login para continuar.</p>
          <button type="button" className="btn-primary" onClick={onContinue}>
            Entrar agora
          </button>
        </>
      )}
      {status === "error" && (
        <>
          <h1 className="auth-title">Não foi possível confirmar</h1>
          <p className="auth-subtitle">{errorMsg}</p>
          <p className="auth-subtitle">
            O link pode ter expirado (24h) ou já ter sido usado. Tente fazer login —
            se precisar, peça um novo link na tela "Esqueci minha senha".
          </p>
          <button type="button" className="btn-primary" onClick={onContinue}>
            Voltar ao login
          </button>
        </>
      )}
    </>
  );
}

/* ───────────────────────────────────── FORGOT */

function ForgotPanel({ initialEmail, onSubmitEmail, onSent, onBackToLogin }) {
  const [email, setEmail] = useState(initialEmail);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    onSubmitEmail(email);
    await postJson("/api/auth/forgot-password", { email });
    setSubmitting(false);
    onSent();
  }

  return (
    <>
      <p className="eyebrow">GFIP</p>
      <h1 className="auth-title">Recuperar senha</h1>
      <p className="auth-subtitle">Enviaremos um link de redefinição para o e-mail informado.</p>
      <form className="login-form" onSubmit={handleSubmit}>
        <label className="field">
          <span className="field-label">E-mail cadastrado</span>
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? "Enviando…" : "Enviar link"}
        </button>
      </form>
      <div className="auth-links">
        <button type="button" className="auth-link" onClick={onBackToLogin}>
          Voltar ao login
        </button>
      </div>
    </>
  );
}

function ForgotSentPanel({ email, onBackToLogin }) {
  return (
    <>
      <p className="eyebrow">GFIP</p>
      <h1 className="auth-title">Confira seu e-mail</h1>
      <p className="auth-subtitle">
        Se <strong>{email}</strong> estiver cadastrado, enviamos um link de redefinição.
        O link é válido por 1 hora.
      </p>
      <div className="auth-info">
        Não recebeu? Cheque a pasta de spam.
      </div>
      <button type="button" className="btn-primary" onClick={onBackToLogin}>
        Voltar ao login
      </button>
    </>
  );
}

/* ───────────────────────────────────── RESET (?reset=TOKEN) */

function ResetPanel({ token, onResetDone }) {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Senha precisa ter pelo menos ${MIN_PASSWORD_LENGTH} caracteres.`);
      return;
    }
    if (password !== confirmPassword) {
      setError("As senhas não coincidem.");
      return;
    }
    setSubmitting(true);
    const r = await postJson("/api/auth/reset-password", {
      token,
      new_password: password,
    });
    setSubmitting(false);
    if (!r.ok) {
      setError(r.payload?.detail ?? "Não foi possível redefinir a senha.");
      return;
    }
    setDone(true);
  }

  if (done) {
    return (
      <>
        <p className="eyebrow">GFIP</p>
        <h1 className="auth-title">Senha redefinida</h1>
        <p className="auth-subtitle">Sua senha foi atualizada. Faça login com a nova senha.</p>
        <button type="button" className="btn-primary" onClick={onResetDone}>
          Entrar agora
        </button>
      </>
    );
  }

  return (
    <>
      <p className="eyebrow">GFIP</p>
      <h1 className="auth-title">Nova senha</h1>
      <p className="auth-subtitle">Defina uma nova senha para sua conta.</p>
      <form className="login-form" onSubmit={handleSubmit}>
        <label className="field">
          <span className="field-label">Nova senha (mínimo {MIN_PASSWORD_LENGTH} caracteres)</span>
          <input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={MIN_PASSWORD_LENGTH}
          />
        </label>
        <label className="field">
          <span className="field-label">Confirmar nova senha</span>
          <input
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
          />
        </label>
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? "Redefinindo…" : "Redefinir e entrar"}
        </button>
      </form>
      {error && <p className="auth-error">{error}</p>}
    </>
  );
}
