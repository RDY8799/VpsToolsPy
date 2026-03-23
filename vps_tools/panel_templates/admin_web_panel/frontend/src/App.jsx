import {useEffect, useMemo, useRef, useState} from "react";

const TABS = [
  {id: "dashboard", label: "Visão geral"},
  {id: "actions", label: "Ações"},
  {id: "tasks", label: "Tarefas"},
  {id: "about", label: "Sobre"}
];

async function apiFetch(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

function LoginForm({onLogin, loading, error}) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");

  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="eyebrow">VpsToolsPy</div>
        <h1>Painel web administrativo</h1>
        <p>Faça login para acompanhar o servidor, abrir tarefas e executar automações com progresso em tempo real.</p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            onLogin({username, password});
          }}
          className="stack"
        >
          <label>
            Usuário
            <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
          </label>
          <label>
            Senha
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
          </label>
          {error ? <div className="error-box">{error}</div> : null}
          <button className="primary-button" type="submit" disabled={loading}>
            {loading ? "Entrando..." : "Entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}

function App() {
  const [auth, setAuth] = useState({authenticated: false});
  const [loadingAuth, setLoadingAuth] = useState(true);
  const [loginError, setLoginError] = useState("");
  const [overview, setOverview] = useState(null);
  const [actions, setActions] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [selectedTaskId, setSelectedTaskId] = useState(null);
  const [submittingAction, setSubmittingAction] = useState("");
  const eventSources = useRef({});

  const selectedTask = useMemo(
    () => tasks.find((task) => task.id === selectedTaskId) || tasks[0] || null,
    [selectedTaskId, tasks]
  );

  const loadApp = async () => {
    const [overviewData, actionsData, tasksData] = await Promise.all([
      apiFetch("/api/overview"),
      apiFetch("/api/actions"),
      apiFetch("/api/tasks")
    ]);
    setOverview(overviewData);
    setActions(actionsData.actions || []);
    setTasks(tasksData.tasks || []);
  };

  const refreshAuth = async () => {
    try {
      const me = await apiFetch("/api/auth/me");
      setAuth(me);
      if (me.authenticated) {
        await loadApp();
      }
    } catch (error) {
      setAuth({authenticated: false});
    } finally {
      setLoadingAuth(false);
    }
  };

  useEffect(() => {
    refreshAuth();
  }, []);

  useEffect(() => {
    if (!auth.authenticated) {
      return undefined;
    }
    const interval = setInterval(() => {
      loadApp().catch(() => undefined);
    }, 30000);
    return () => clearInterval(interval);
  }, [auth.authenticated]);

  useEffect(() => {
    if (!selectedTask) {
      return undefined;
    }
    if (selectedTask.state === "completed" || selectedTask.state === "failed") {
      return undefined;
    }
    if (eventSources.current[selectedTask.id]) {
      return undefined;
    }
    const source = new EventSource(`/api/tasks/${selectedTask.id}/stream`);
    eventSources.current[selectedTask.id] = source;
    source.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      setTasks((current) =>
        current.map((task) => {
          if (task.id !== selectedTask.id) {
            return task;
          }
          const nextEvents = [...(task.events || []), payload];
          const next = {...task, events: nextEvents};
          if (payload.type === "progress") {
            next.progress = payload.percent ?? task.progress;
            next.message = payload.message || task.message;
            next.state = "running";
          }
          if (payload.type === "started") {
            next.state = "running";
            next.message = "Execução iniciada";
          }
          if (payload.type === "result") {
            next.state = payload.ok ? "completed" : "failed";
            next.result = payload.data;
            next.message = payload.ok ? "Concluído" : "Falhou";
            next.progress = payload.ok ? 100 : next.progress;
          }
          return next;
        })
      );
    };
    source.onerror = () => {
      source.close();
      delete eventSources.current[selectedTask.id];
    };
    return () => {
      source.close();
      delete eventSources.current[selectedTask.id];
    };
  }, [selectedTask]);

  const handleLogin = async ({username, password}) => {
    try {
      setLoginError("");
      setLoadingAuth(true);
      await apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({username, password})
      });
      await refreshAuth();
    } catch (error) {
      setLoginError("Credenciais inválidas.");
      setLoadingAuth(false);
    }
  };

  const handleLogout = async () => {
    await apiFetch("/api/auth/logout", {method: "POST"});
    setAuth({authenticated: false});
    setOverview(null);
    setTasks([]);
    setActions([]);
  };

  const handleRunAction = async (actionId, formData) => {
    try {
      setSubmittingAction(actionId);
      const task = await apiFetch("/api/tasks", {
        method: "POST",
        body: JSON.stringify({action: actionId, params: formData})
      });
      setTasks((current) => [task, ...current]);
      setSelectedTaskId(task.id);
      setActiveTab("tasks");
    } finally {
      setSubmittingAction("");
    }
  };

  if (loadingAuth) {
    return <div className="loading-screen">Carregando painel...</div>;
  }

  if (!auth.authenticated) {
    return <LoginForm onLogin={handleLogin} loading={loadingAuth} error={loginError} />;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <div className="eyebrow">Painel</div>
          <h2>VpsToolsPy</h2>
          <p>Operação visual do servidor com execução assistida e histórico de tarefas.</p>
        </div>
        <nav className="nav-stack">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              className={activeTab === tab.id ? "nav-item active" : "nav-item"}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </nav>
        <button className="ghost-button" onClick={handleLogout}>Sair</button>
      </aside>

      <main className="content-shell">
        <header className="topbar">
          <div>
            <div className="eyebrow">Usuário autenticado</div>
            <strong>{auth.username}</strong>
          </div>
          <div className="status-pill">{overview?.panel?.scriptVersion || "unknown"}</div>
        </header>

        {activeTab === "dashboard" ? <Dashboard overview={overview} /> : null}
        {activeTab === "actions" ? (
          <ActionsPanel actions={actions} runningAction={submittingAction} onRunAction={handleRunAction} />
        ) : null}
        {activeTab === "tasks" ? (
          <TasksPanel tasks={tasks} selectedTask={selectedTask} onSelectTask={setSelectedTaskId} />
        ) : null}
        {activeTab === "about" ? <AboutPanel overview={overview} /> : null}
      </main>
    </div>
  );
}

function Dashboard({overview}) {
  if (!overview) {
    return <div className="panel-card">Carregando visão geral...</div>;
  }
  const data = overview.overview;
  return (
    <div className="grid-layout">
      <section className="panel-card hero-card">
        <div className="eyebrow">Servidor</div>
        <h1>{data.script.hostname}</h1>
        <p>{data.script.os}</p>
        <div className="pill-row">
          <span className="status-pill">IP {data.script.public_ip}</span>
          <span className="status-pill">Python {data.script.python}</span>
        </div>
      </section>
      <section className="panel-card">
        <h3>Saúde do host</h3>
        <div className="metric-grid">
          <Metric label="CPU" value={`${data.system.cpu_percent}%`} />
          <Metric label="RAM livre" value={`${data.system.ram.free} MB`} />
          <Metric label="RAM total" value={`${data.system.ram.total} MB`} />
          <Metric label="Swap livre" value={`${data.system.swap.free} MB`} />
        </div>
      </section>
      <section className="panel-card full-span">
        <h3>Componentes</h3>
        <table className="table">
          <thead>
          <tr>
            <th>Recurso</th>
            <th>Instalado</th>
            <th>Status</th>
          </tr>
          </thead>
          <tbody>
          {data.components.map((component) => (
            <tr key={component.key}>
              <td>{component.name}</td>
              <td>{component.installed ? "Sim" : "Não"}</td>
              <td><span className={component.active ? "state-green" : "state-red"}>{component.status}</span></td>
            </tr>
          ))}
          </tbody>
        </table>
      </section>
      <section className="panel-card full-span">
        <h3>Portas abertas</h3>
        <table className="table">
          <thead>
          <tr>
            <th>Proto</th>
            <th>Host</th>
            <th>Porta</th>
            <th>Processo</th>
          </tr>
          </thead>
          <tbody>
          {data.open_ports.map((port) => (
            <tr key={`${port.protocol}-${port.host}-${port.port}`}>
              <td>{port.protocol}</td>
              <td>{port.host}</td>
              <td>{port.port}</td>
              <td>{port.process}</td>
            </tr>
          ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function Metric({label, value}) {
  return (
    <div className="metric-card">
      <small>{label}</small>
      <strong>{value}</strong>
    </div>
  );
}

function ActionsPanel({actions, onRunAction, runningAction}) {
  return (
    <div className="actions-grid">
      {actions.map((action) => (
        <ActionCard key={action.id} action={action} onRunAction={onRunAction} running={runningAction === action.id} />
      ))}
    </div>
  );
}

function ActionCard({action, onRunAction, running}) {
  const [form, setForm] = useState(() => {
    const initial = {};
    action.schema.forEach((field) => {
      initial[field.name] = field.default ?? (field.type === "boolean" ? false : "");
    });
    return initial;
  });

  return (
    <section className="panel-card action-card">
      <div className="eyebrow">{action.category}</div>
      <h3>{action.label}</h3>
      <p>{action.description}</p>
      <form
        className="stack"
        onSubmit={(event) => {
          event.preventDefault();
          onRunAction(action.id, form);
        }}
      >
        {action.schema.map((field) => (
          <Field
            key={field.name}
            field={field}
            value={form[field.name]}
            onChange={(value) => setForm((current) => ({...current, [field.name]: value}))}
          />
        ))}
        <button className="primary-button" type="submit" disabled={running}>
          {running ? "Enviando..." : "Executar"}
        </button>
      </form>
    </section>
  );
}

function Field({field, value, onChange}) {
  if (field.type === "boolean") {
    return (
      <label className="toggle-field">
        <span>{field.label}</span>
        <input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />
      </label>
    );
  }
  if (field.type === "select") {
    return (
      <label>
        {field.label}
        <select value={value} onChange={(event) => onChange(event.target.value)}>
          {(field.options || []).map((option) => (
            <option value={option} key={option}>{option}</option>
          ))}
        </select>
      </label>
    );
  }
  if (field.type === "textarea") {
    return (
      <label>
        {field.label}
        <textarea value={value} onChange={(event) => onChange(event.target.value)} rows={4} />
      </label>
    );
  }
  return (
    <label>
      {field.label}
      <input
        type={field.type === "password" ? "password" : field.type === "number" ? "number" : "text"}
        value={value}
        onChange={(event) => onChange(field.type === "number" ? Number(event.target.value) : event.target.value)}
      />
    </label>
  );
}

function TasksPanel({tasks, selectedTask, onSelectTask}) {
  return (
    <div className="task-layout">
      <section className="panel-card">
        <h3>Tarefas recentes</h3>
        <div className="task-list">
          {tasks.map((task) => (
            <button
              key={task.id}
              className={selectedTask?.id === task.id ? "task-item active" : "task-item"}
              onClick={() => onSelectTask(task.id)}
            >
              <strong>{task.action}</strong>
              <span>{task.message}</span>
              <small>{task.state}</small>
            </button>
          ))}
        </div>
      </section>
      <section className="panel-card">
        {selectedTask ? (
          <>
            <h3>{selectedTask.action}</h3>
            <div className="progress-bar">
              <div style={{width: `${selectedTask.progress || 0}%`}} />
            </div>
            <p>{selectedTask.message}</p>
            <pre className="log-box">
              {(selectedTask.events || []).map((event, index) => JSON.stringify(event, null, 2)).join("\n\n")}
            </pre>
          </>
        ) : (
          <p>Nenhuma tarefa enviada ainda.</p>
        )}
      </section>
    </div>
  );
}

function AboutPanel({overview}) {
  if (!overview) {
    return <div className="panel-card">Carregando metadados...</div>;
  }
  return (
    <section className="panel-card">
      <div className="eyebrow">Sobre o projeto</div>
      <h2>VpsToolsPy Admin Panel</h2>
      <p>
        Interface web do script para inventário, operação assistida e execução de automações com
        acompanhamento de progresso pelo navegador.
      </p>
      <ul className="about-list">
        <li>Script version: {overview.panel.scriptVersion}</li>
        <li>Panel version: {overview.panel.panelVersion}</li>
        <li>Repo dir: {overview.panel.repoDir}</li>
        <li>Python command: {overview.panel.pythonCommand}</li>
      </ul>
    </section>
  );
}

export default App;
