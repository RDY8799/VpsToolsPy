import {useEffect, useMemo, useRef, useState} from "react";

const TABS = [
  {id: "dashboard", label: "Dashboard", kicker: "Resumo visual"},
  {id: "actions", label: "Automacoes", kicker: "Executar tarefas"},
  {id: "tasks", label: "Fila de tarefas", kicker: "Progresso em tempo real"},
  {id: "about", label: "Sobre", kicker: "Metadados do painel"}
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
      <div className="login-orb login-orb-left" />
      <div className="login-orb login-orb-right" />
      <div className="login-card">
        <div className="eyebrow">VpsToolsPy</div>
        <h1>Painel administrativo</h1>
        <p>
          Acesse o servidor, acompanhe recursos instalados, execute automacoes
          e veja o progresso sem ficar preso ao terminal.
        </p>
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            onLogin({username, password});
          }}
        >
          <label>
            Usuario
            <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
          </label>
          <label>
            Senha
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
          </label>
          {error ? <div className="error-box">{error}</div> : null}
          <button className="primary-button" type="submit" disabled={loading}>
            {loading ? "Entrando..." : "Entrar no painel"}
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
    } catch {
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
            next.message = "Execucao iniciada";
          }
          if (payload.type === "result") {
            next.state = payload.ok ? "completed" : "failed";
            next.result = payload.data;
            next.message = payload.ok ? "Concluido" : "Falhou";
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
    } catch {
      setLoginError("Credenciais invalidas.");
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
        <div className="sidebar-brand">
          <div className="brand-mark">VT</div>
          <div>
            <div className="eyebrow">Painel operacional</div>
            <h2>VpsToolsPy</h2>
            <p>Controle visual para deploy, banco, monitoramento e DR.</p>
          </div>
        </div>

        <div className="sidebar-group">
          <div className="section-label">Navegacao</div>
          <nav className="nav-stack">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                className={activeTab === tab.id ? "nav-item active" : "nav-item"}
                onClick={() => setActiveTab(tab.id)}
              >
                <strong>{tab.label}</strong>
                <small>{tab.kicker}</small>
              </button>
            ))}
          </nav>
        </div>

        <div className="sidebar-group">
          <div className="section-label">Sessao</div>
          <div className="sidebar-card">
            <div className="status-row">
              <span>Usuario</span>
              <strong>{auth.username}</strong>
            </div>
            <div className="status-row">
              <span>Versao do script</span>
              <strong>{overview?.panel?.scriptVersion || "unknown"}</strong>
            </div>
            <div className="status-row">
              <span>Tarefas recentes</span>
              <strong>{tasks.length}</strong>
            </div>
            <button className="ghost-button logout-button" onClick={handleLogout}>
              Sair do painel
            </button>
          </div>
        </div>
      </aside>

      <main className="content-shell">
        <header className="topbar panel-card">
          <div>
            <div className="eyebrow">Visao atual</div>
            <h1>{TABS.find((tab) => tab.id === activeTab)?.label || "Painel"}</h1>
            <p className="topbar-copy">
              Layout grafico para acompanhar o servidor, executar automacoes e verificar tudo o que esta ativo.
            </p>
          </div>
          <div className="topbar-side">
            <div className="status-pill">Host {overview?.overview?.script?.hostname || "unknown"}</div>
            <div className="status-pill accent">{overview?.overview?.script?.public_ip || "sem IP"}</div>
          </div>
        </header>

        {activeTab === "dashboard" ? <Dashboard overview={overview} tasks={tasks} /> : null}
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

function Dashboard({overview, tasks}) {
  if (!overview) {
    return <div className="panel-card">Carregando visao geral...</div>;
  }

  const data = overview.overview;
  const activeComponents = data.components.filter((item) => item.active).length;
  const installedComponents = data.components.filter((item) => item.installed).length;
  const runningTasks = tasks.filter((task) => task.state === "running").length;
  const topPorts = data.open_ports.slice(0, 8);

  return (
    <div className="dashboard-layout">
      <section className="panel-card hero-card">
        <div className="hero-grid">
          <div>
            <div className="eyebrow">Host principal</div>
            <h2>{data.script.hostname}</h2>
            <p className="hero-copy">
              Ambiente visual para administrar recursos do script, acompanhar o estado do host e disparar tarefas com retorno em tempo real.
            </p>
            <div className="pill-row">
              <span className="status-pill">SO {data.script.os}</span>
              <span className="status-pill">Python {data.script.python}</span>
            </div>
          </div>
          <div className="hero-stats">
            <Metric tone="teal" label="Ativos agora" value={String(activeComponents)} hint="componentes respondendo" />
            <Metric tone="amber" label="Instalados" value={String(installedComponents)} hint="componentes detectados" />
            <Metric tone="ink" label="Tarefas rodando" value={String(runningTasks)} hint="execucoes em progresso" />
          </div>
        </div>
      </section>

      <section className="panel-card dashboard-health">
        <div className="card-header">
          <div>
            <div className="eyebrow">Saude</div>
            <h3>Recursos do host</h3>
          </div>
        </div>
        <div className="metric-grid metric-grid-dense">
          <Metric tone="teal" label="CPU" value={`${data.system.cpu_percent}%`} hint="uso atual" />
          <Metric tone="ink" label="RAM livre" value={`${data.system.ram.free} MB`} hint={`de ${data.system.ram.total} MB`} />
          <Metric tone="amber" label="RAM usada" value={`${data.system.ram.used} MB`} hint={`${data.system.ram.percent}% ocupada`} />
          <Metric tone="ink" label="Swap livre" value={`${data.system.swap.free} MB`} hint={`de ${data.system.swap.total} MB`} />
        </div>
      </section>

      <section className="panel-card dashboard-ports">
        <div className="card-header">
          <div>
            <div className="eyebrow">Acesso</div>
            <h3>Portas abertas</h3>
          </div>
          <span className="count-pill">{data.open_ports.length}</span>
        </div>
        <div className="port-list port-grid">
          {topPorts.length ? topPorts.map((port) => (
            <div className="port-card" key={`${port.protocol}-${port.host}-${port.port}`}>
              <div className="port-card-top">
                <strong>{port.port || "-"}</strong>
                <span>{port.protocol}</span>
              </div>
              <small>{port.host}</small>
              <p>{port.process || "processo nao informado"}</p>
            </div>
          )) : <div className="empty-box">Nenhuma porta listada neste momento.</div>}
        </div>
        {data.open_ports.length > topPorts.length ? (
          <div className="section-footnote">Mostrando as {topPorts.length} primeiras portas detectadas.</div>
        ) : null}
      </section>

      <section className="panel-card full-span">
        <div className="card-header">
          <div>
            <div className="eyebrow">Inventario</div>
            <h3>Componentes do servidor</h3>
          </div>
          <span className="count-pill">{data.components.length}</span>
        </div>
        <div className="component-grid">
          {data.components.map((component) => (
            <div className="component-card" key={component.key}>
              <div className="component-card-top">
                <strong>{component.name}</strong>
                <span className={component.active ? "state-pill state-pill-green" : "state-pill state-pill-red"}>
                  {component.status}
                </span>
              </div>
              <div className="component-meta">
                <span>{component.installed ? "Instalado" : "Nao instalado"}</span>
                <span>{component.active ? "Respondendo" : "Parado ou indisponivel"}</span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Metric({label, value, hint, tone = "ink"}) {
  return (
    <div className={`metric-card metric-${tone}`}>
      <small>{label}</small>
      <strong>{value}</strong>
      <span>{hint}</span>
    </div>
  );
}

function ActionsPanel({actions, onRunAction, runningAction}) {
  const [selectedActionId, setSelectedActionId] = useState(actions[0]?.id || "");

  useEffect(() => {
    if (!actions.length) {
      setSelectedActionId("");
      return;
    }
    if (!actions.some((action) => action.id === selectedActionId)) {
      setSelectedActionId(actions[0].id);
    }
  }, [actions, selectedActionId]);

  const selectedAction = actions.find((action) => action.id === selectedActionId) || actions[0] || null;

  return (
    <div className="actions-layout">
      <section className="panel-card section-intro">
        <div className="eyebrow">Catalogo</div>
        <h2>Automacoes disponiveis</h2>
        <p>
          Cada card representa uma acao operacional do script. Preencha os campos,
          envie e acompanhe a execucao na aba de tarefas.
        </p>
      </section>

      <div className="actions-workspace">
        <section className="panel-card action-browser">
          <div className="card-header">
            <div>
              <div className="eyebrow">Escolha uma automacao</div>
              <h3>Catalogo de acoes</h3>
            </div>
            <span className="count-pill">{actions.length}</span>
          </div>

          <div className="action-browser-list">
            {actions.map((action) => (
              <button
                key={action.id}
                className={selectedAction?.id === action.id ? "action-summary-card active" : "action-summary-card"}
                onClick={() => setSelectedActionId(action.id)}
              >
                <div className="action-summary-top">
                  <strong>{action.label}</strong>
                  <span className="count-pill">{action.schema.length}</span>
                </div>
                <small>{action.category}</small>
                <p>{action.description}</p>
              </button>
            ))}
          </div>
        </section>

        <section className="panel-card action-stage">
          {selectedAction ? (
            <ActionCard
              key={selectedAction.id}
              action={selectedAction}
              onRunAction={onRunAction}
              running={runningAction === selectedAction.id}
            />
          ) : (
            <div className="empty-box">Nenhuma automacao disponivel no momento.</div>
          )}
        </section>
      </div>
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
    <section className="action-card">
      <div className="action-card-head">
        <div>
          <div className="eyebrow">{action.category}</div>
          <h3>{action.label}</h3>
        </div>
        <span className="count-pill">{action.schema.length} campos</span>
      </div>
      <p>{action.description}</p>
      <form
        className="stack"
        onSubmit={(event) => {
          event.preventDefault();
          onRunAction(action.id, form);
        }}
      >
        <div className="form-grid">
          {action.schema.map((field) => (
            <Field
              key={field.name}
              field={field}
              value={form[field.name]}
              onChange={(value) => setForm((current) => ({...current, [field.name]: value}))}
            />
          ))}
        </div>
        <button className="primary-button" type="submit" disabled={running}>
          {running ? "Enviando..." : "Executar automacao"}
        </button>
      </form>
    </section>
  );
}

function Field({field, value, onChange}) {
  if (field.type === "boolean") {
    return (
      <label className="toggle-field full-width-field">
        <div>
          <strong>{field.label}</strong>
          <small>Alterna este comportamento na execucao.</small>
        </div>
        <input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />
      </label>
    );
  }

  if (field.type === "select") {
    return (
      <label>
        <span className="field-label">{field.label}</span>
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
      <label className="full-width-field">
        <span className="field-label">{field.label}</span>
        <textarea value={value} onChange={(event) => onChange(event.target.value)} rows={4} />
      </label>
    );
  }

  return (
    <label>
      <span className="field-label">{field.label}</span>
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
      <section className="panel-card task-rail">
        <div className="card-header">
          <div>
            <div className="eyebrow">Fila</div>
            <h3>Tarefas recentes</h3>
          </div>
          <span className="count-pill">{tasks.length}</span>
        </div>
        <div className="task-list">
          {tasks.length ? tasks.map((task) => (
            <button
              key={task.id}
              className={selectedTask?.id === task.id ? "task-item active" : "task-item"}
              onClick={() => onSelectTask(task.id)}
            >
              <div className="task-item-top">
                <strong>{task.action}</strong>
                <span className={`state-pill ${task.state === "completed" ? "state-pill-green" : task.state === "failed" ? "state-pill-red" : "state-pill-amber"}`}>
                  {task.state}
                </span>
              </div>
              <span>{task.message}</span>
              <small>{task.id}</small>
            </button>
          )) : <div className="empty-box">Nenhuma tarefa enviada ainda.</div>}
        </div>
      </section>

      <section className="panel-card task-stage">
        {selectedTask ? (
          <>
            <div className="card-header">
              <div>
                <div className="eyebrow">Execucao selecionada</div>
                <h3>{selectedTask.action}</h3>
              </div>
              <span className="count-pill">{selectedTask.progress || 0}%</span>
            </div>

            <div className="task-summary-grid">
              <Metric tone="teal" label="Estado" value={selectedTask.state} hint="status atual" />
              <Metric tone="amber" label="Progresso" value={`${selectedTask.progress || 0}%`} hint="etapa concluida" />
              <Metric tone="ink" label="Eventos" value={String((selectedTask.events || []).length)} hint="linhas recebidas" />
            </div>

            <div className="progress-bar">
              <div style={{width: `${selectedTask.progress || 0}%`}} />
            </div>

            <p className="task-message">{selectedTask.message}</p>
            <pre className="log-box">
              {(selectedTask.events || []).map((event) => JSON.stringify(event, null, 2)).join("\n\n")}
            </pre>
          </>
        ) : (
          <div className="empty-box">Selecione uma tarefa para ver o progresso detalhado.</div>
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
    <div className="about-layout">
      <section className="panel-card">
        <div className="eyebrow">Painel</div>
        <h2>VpsToolsPy Admin Panel</h2>
        <p>
          Interface web do script para inventario, operacao assistida, deploy,
          banco de dados, monitoramento e recuperacao.
        </p>
      </section>

      <section className="panel-card">
        <div className="card-header">
          <div>
            <div className="eyebrow">Metadados</div>
            <h3>Informacoes tecnicas</h3>
          </div>
        </div>
        <div className="info-list">
          <InfoRow label="Script version" value={overview.panel.scriptVersion} />
          <InfoRow label="Panel version" value={overview.panel.panelVersion} />
          <InfoRow label="Repo dir" value={overview.panel.repoDir} />
          <InfoRow label="Python command" value={overview.panel.pythonCommand} />
        </div>
      </section>
    </div>
  );
}

function InfoRow({label, value}) {
  return (
    <div className="info-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default App;
