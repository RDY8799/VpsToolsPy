import {useDeferredValue, useEffect, useMemo, useRef, useState} from "react";

const TABS = [
  {id: "overview", label: "Panorama", kicker: "Visao executiva"},
  {id: "operations", label: "Operacoes", kicker: "Executar automacoes"},
  {id: "fleet", label: "Servicos", kicker: "Infra, usuarios e DR"},
  {id: "tasks", label: "Tarefas", kicker: "Fila em tempo real"},
  {id: "about", label: "Sobre", kicker: "Metadados do painel"}
];

const CATEGORY_META = {
  services: {label: "Servicos"},
  users: {label: "Usuarios"},
  database: {label: "Banco"},
  backend: {label: "Backend"},
  infra: {label: "Infra"},
  panels: {label: "Paineis"},
  system: {label: "Sistema"},
  dr: {label: "DR"}
};

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

function formatDate(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(date);
}

function pretty(value) {
  if (value == null) {
    return "-";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value, null, 2);
}

function LoginForm({onLogin, loading, error}) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");

  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="eyebrow">VpsToolsPy Platform</div>
        <h1>Centro operacional da VPS</h1>
        <p>
          Um painel unico para inventario, servicos, banco, backend,
          usuarios SSH, tarefas e recuperacao.
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
  const [activeTab, setActiveTab] = useState("overview");
  const [selectedTaskId, setSelectedTaskId] = useState(null);
  const [submittingAction, setSubmittingAction] = useState("");
  const [appError, setAppError] = useState("");
  const [actionPreset, setActionPreset] = useState(null);
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

  const handleRunAction = async (actionId, formData, nextTab = "tasks") => {
    try {
      setSubmittingAction(actionId);
      setAppError("");
      const task = await apiFetch("/api/tasks", {
        method: "POST",
        body: JSON.stringify({action: actionId, params: formData})
      });
      setTasks((current) => [task, ...current]);
      setSelectedTaskId(task.id);
      setActiveTab(nextTab);
      return task;
    } catch (error) {
      setAppError(error.message || "Falha ao enviar automacao.");
      throw error;
    } finally {
      setSubmittingAction("");
    }
  };

  const openAction = (actionId, params = {}) => {
    setActionPreset({actionId, params, nonce: Date.now()});
    setActiveTab("operations");
  };

  if (loadingAuth) {
    return <div className="loading-screen">Carregando plataforma...</div>;
  }

  if (!auth.authenticated) {
    return <LoginForm onLogin={handleLogin} loading={loadingAuth} error={loginError} />;
  }

  const data = overview?.overview;
  const runningTasks = tasks.filter((task) => task.state === "running").length;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark">VP</div>
          <div>
            <div className="eyebrow">Plataforma operacional</div>
            <h2>VpsToolsPy</h2>
            <p>Infra, banco, backend, servicos e DR em uma unica camada de operacao.</p>
          </div>
        </div>

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

        <div className="sidebar-card">
          <div className="section-label">Sessao</div>
          <div className="status-row"><span>Usuario</span><strong>{auth.username}</strong></div>
          <div className="status-row"><span>Tarefas rodando</span><strong>{runningTasks}</strong></div>
          <div className="status-row"><span>Host</span><strong>{data?.script?.hostname || "unknown"}</strong></div>
          <button className="ghost-button logout-button" onClick={handleLogout}>Sair</button>
        </div>
      </aside>

      <main className="content-shell">
        <header className="topbar panel-card">
          <div>
            <div className="eyebrow">Centro de operacoes</div>
            <h1>{TABS.find((tab) => tab.id === activeTab)?.label || "Painel"}</h1>
            <p className="topbar-copy">O painel agora concentra diagnostico, acao, execucao e leitura operacional do host.</p>
          </div>
          <div className="topbar-side">
            <span className="status-pill">Host {data?.script?.hostname || "unknown"}</span>
            <span className="status-pill">Script {overview?.panel?.scriptVersion || "unknown"}</span>
            <span className="status-pill accent">{data?.script?.public_ip || "sem IP"}</span>
          </div>
        </header>

        {appError ? <div className="error-box">{appError}</div> : null}

        {activeTab === "overview" ? (
          <OverviewPanel overview={overview} tasks={tasks} onQuickRun={handleRunAction} onOpenAction={openAction} />
        ) : null}
        {activeTab === "operations" ? (
          <OperationsPanel
            actions={actions}
            runningAction={submittingAction}
            onRunAction={handleRunAction}
            preset={actionPreset}
          />
        ) : null}
        {activeTab === "fleet" ? (
          <FleetPanel overview={overview} onQuickRun={handleRunAction} onOpenAction={openAction} />
        ) : null}
        {activeTab === "tasks" ? (
          <TasksPanel tasks={tasks} selectedTask={selectedTask} onSelectTask={setSelectedTaskId} />
        ) : null}
        {activeTab === "about" ? <AboutPanel overview={overview} actions={actions} /> : null}
      </main>
    </div>
  );
}

function StatCard({label, value, hint, tone = "neutral"}) {
  return (
    <div className={`stat-card stat-${tone}`}>
      <small>{label}</small>
      <strong>{value}</strong>
      <span>{hint}</span>
    </div>
  );
}

function OverviewPanel({overview, tasks, onQuickRun, onOpenAction}) {
  if (!overview) {
    return <div className="panel-card">Carregando visao geral...</div>;
  }

  const data = overview.overview;
  const runningTasks = tasks.filter((task) => task.state === "running").length;
  const topServices = (data.managed_services || []).slice(0, 6);
  const topUsers = (data.users?.items || []).slice(0, 5);
  const topJobs = (data.backups?.items || []).slice(0, 4);

  return (
    <div className="page-grid">
      <section className="hero-board panel-card">
        <div>
          <div className="eyebrow">Host principal</div>
          <h2>{data.script.hostname}</h2>
          <p>
            Plataforma visual para operar a VPS com mais contexto, menos navegacao cega
            e mais acoes executaveis a partir do navegador.
          </p>
          <div className="pill-row">
            <span className="status-pill">SO {data.script.os}</span>
            <span className="status-pill">Python {data.script.python}</span>
            <span className="status-pill">Servicos {data.highlights.managed_services_active}/{data.highlights.managed_services_installed}</span>
          </div>
        </div>
        <div className="stat-grid">
          <StatCard label="CPU" value={`${data.system.cpu_percent}%`} hint="uso atual" tone="teal" />
          <StatCard label="Usuarios SSH" value={String(data.users.count)} hint={`${data.users.connected_count} conectados`} tone="amber" />
          <StatCard label="Backups" value={String(data.backups.count)} hint={`${data.backups.healthy_count} saudaveis`} tone="neutral" />
          <StatCard label="Tarefas" value={String(runningTasks)} hint="rodando agora" tone="ink" />
        </div>
      </section>

      <section className="panel-card">
        <div className="section-head">
          <div><div className="eyebrow">Acoes rapidas</div><h3>Centros de operacao</h3></div>
        </div>
        <div className="quick-grid">
          <button className="quick-card" onClick={() => onOpenAction("panels.install_admin_web_panel")}>
            <strong>Painel administrativo</strong>
            <span>Instalar, reconstruir e endurecer o deploy.</span>
          </button>
          <button className="quick-card" onClick={() => onOpenAction("database.install_postgresql")}>
            <strong>Banco principal</strong>
            <span>Provisionar PostgreSQL e preparar JDBC.</span>
          </button>
          <button className="quick-card" onClick={() => onOpenAction("backend.prepare_spring_boot")}>
            <strong>Backend</strong>
            <span>Preparar runtime, variaveis e padrao operacional.</span>
          </button>
          <button className="quick-card" onClick={() => onOpenAction("system.update_packages")}>
            <strong>Sistema</strong>
            <span>Rodar manutencao de pacotes e limpeza.</span>
          </button>
        </div>
      </section>

      <section className="panel-card">
        <div className="section-head">
          <div><div className="eyebrow">Servicos</div><h3>Fleet operacional</h3></div>
        </div>
        <div className="service-grid">
          {topServices.map((service) => (
            <article className="service-card" key={service.key}>
              <div className="service-head">
                <strong>{service.name}</strong>
                <span className={`state-pill ${service.active ? "state-pill-green" : "state-pill-red"}`}>{service.status}</span>
              </div>
              <small>{service.family}</small>
              <p>{Array.isArray(service.ports) ? service.ports.join(", ") || "sem portas detectadas" : "portas compostas"}</p>
              <div className="button-row">
                <button className="mini-button" onClick={() => onQuickRun("services.manage", {service_key: service.key, operation: "status"})}>Status</button>
                <button className="mini-button" onClick={() => onQuickRun("services.manage", {service_key: service.key, operation: "restart"})}>Restart</button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="panel-card">
        <div className="section-head">
          <div><div className="eyebrow">Usuarios</div><h3>SSH gerenciado</h3></div>
          <span className="count-pill">{data.users.count}</span>
        </div>
        <div className="table-like">
          {topUsers.map((user) => (
            <div className="list-row" key={user.username}>
              <div>
                <strong>{user.username}</strong>
                <small>expira: {user.expiry}</small>
              </div>
              <div className="list-row-side">
                <span>limite {user.limit}</span>
                <span>{user.connected} online</span>
                <button className="mini-button" onClick={() => onQuickRun("users.disconnect", {username: user.username})}>Desconectar</button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel-card full-span">
        <div className="section-head">
          <div><div className="eyebrow">Backups e rede</div><h3>Postura operacional</h3></div>
        </div>
        <div className="split-grid">
          <div className="subpanel">
            <h4>Jobs de backup</h4>
            {topJobs.length ? topJobs.map((job) => (
              <div className="list-row" key={job.job_name}>
                <div>
                  <strong>{job.job_name}</strong>
                  <small>{job.engine} · {job.last_state}</small>
                </div>
                <button className="mini-button" onClick={() => onQuickRun("dr.run_backup", {job_name: job.job_name})}>Executar</button>
              </div>
            )) : <div className="empty-box">Nenhum job de backup configurado.</div>}
          </div>
          <div className="subpanel">
            <h4>Portas abertas</h4>
            <div className="port-badges">
              {(data.open_ports || []).slice(0, 12).map((port) => (
                <span className="status-pill" key={`${port.protocol}-${port.host}-${port.port}`}>{port.protocol} {port.port || "-"}</span>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function FleetPanel({overview, onQuickRun, onOpenAction}) {
  if (!overview) {
    return <div className="panel-card">Carregando servicos...</div>;
  }
  const data = overview.overview;
  return (
    <div className="page-grid">
      <section className="panel-card">
        <div className="section-head">
          <div><div className="eyebrow">Fleet</div><h3>Servicos gerenciados</h3></div>
        </div>
        <div className="service-grid">
          {(data.managed_services || []).map((service) => (
            <article className="service-card" key={service.key}>
              <div className="service-head">
                <strong>{service.name}</strong>
                <span className={`state-pill ${service.active ? "state-pill-green" : "state-pill-red"}`}>{service.status}</span>
              </div>
              <small>{service.family}</small>
              <p>{pretty(service.details).slice(0, 120)}</p>
              <div className="button-row">
                <button className="mini-button" onClick={() => onQuickRun("services.manage", {service_key: service.key, operation: "start"})}>Start</button>
                <button className="mini-button" onClick={() => onQuickRun("services.manage", {service_key: service.key, operation: "stop"})}>Stop</button>
                <button className="mini-button" onClick={() => onQuickRun("services.manage", {service_key: service.key, operation: "logs"})}>Logs</button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="panel-card">
        <div className="section-head">
          <div><div className="eyebrow">Usuarios e DR</div><h3>Contexto gerencial</h3></div>
        </div>
        <div className="split-grid">
          <div className="subpanel">
            <h4>Usuarios SSH</h4>
            {(data.users?.items || []).map((user) => (
              <div className="list-row" key={user.username}>
                <div>
                  <strong>{user.username}</strong>
                  <small>limite {user.limit} · expira {user.expiry}</small>
                </div>
                <div className="list-row-side">
                  <button className="mini-button" onClick={() => onOpenAction("users.change_password", {username: user.username})}>Senha</button>
                  <button className="mini-button" onClick={() => onOpenAction("users.change_limit", {username: user.username})}>Limite</button>
                </div>
              </div>
            ))}
          </div>
          <div className="subpanel">
            <h4>Recuperacao</h4>
            <div className="info-stack">
              <div className="info-chip">Perfis DR: {data.dr.profiles_count}</div>
              <div className="info-chip">Monitores DR: {data.dr.monitors_count}</div>
              <div className="info-chip">Jobs de backup: {data.backups.count}</div>
            </div>
            <div className="button-row">
              <button className="mini-button" onClick={() => onOpenAction("dr.export_config")}>Exportar configs</button>
              <button className="mini-button" onClick={() => onOpenAction("dr.restore_test")}>Teste restore</button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function OperationsPanel({actions, onRunAction, runningAction, preset}) {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [selectedActionId, setSelectedActionId] = useState(actions[0]?.id || "");
  const deferredSearch = useDeferredValue(search);

  useEffect(() => {
    if (!actions.length) {
      setSelectedActionId("");
      return;
    }
    if (preset?.actionId) {
      setSelectedActionId(preset.actionId);
      return;
    }
    if (!actions.some((action) => action.id === selectedActionId)) {
      setSelectedActionId(actions[0].id);
    }
  }, [actions, selectedActionId, preset]);

  const filteredActions = useMemo(() => {
    return actions.filter((action) => {
      const matchesCategory = category === "all" || action.category === category;
      const haystack = `${action.label} ${action.description} ${action.category}`.toLowerCase();
      const matchesSearch = !deferredSearch || haystack.includes(deferredSearch.toLowerCase());
      return matchesCategory && matchesSearch;
    });
  }, [actions, category, deferredSearch]);

  const selectedAction = filteredActions.find((action) => action.id === selectedActionId)
    || actions.find((action) => action.id === selectedActionId)
    || filteredActions[0]
    || actions[0]
    || null;

  return (
    <div className="page-grid operations-grid">
      <section className="panel-card action-browser">
        <div className="section-head">
          <div><div className="eyebrow">Catalogo</div><h3>Automacoes do script</h3></div>
          <span className="count-pill">{actions.length}</span>
        </div>
        <input placeholder="Buscar acao, dominio ou descricao" value={search} onChange={(event) => setSearch(event.target.value)} />
        <div className="filter-row">
          <button className={category === "all" ? "chip active" : "chip"} onClick={() => setCategory("all")}>Tudo</button>
          {Object.entries(CATEGORY_META).map(([key, meta]) => (
            <button key={key} className={category === key ? "chip active" : "chip"} onClick={() => setCategory(key)}>{meta.label}</button>
          ))}
        </div>
        <div className="action-list">
          {filteredActions.map((action) => (
            <button
              key={action.id}
              className={selectedAction?.id === action.id ? "action-card active" : "action-card"}
              onClick={() => setSelectedActionId(action.id)}
            >
              <strong>{action.label}</strong>
              <small>{CATEGORY_META[action.category]?.label || action.category}</small>
              <p>{action.description}</p>
            </button>
          ))}
        </div>
      </section>

      <section className="panel-card">
        {selectedAction ? (
          <ActionStage action={selectedAction} running={runningAction === selectedAction.id} onRunAction={onRunAction} preset={preset} />
        ) : (
          <div className="empty-box">Nenhuma automacao disponivel.</div>
        )}
      </section>
    </div>
  );
}

function ActionStage({action, onRunAction, running, preset}) {
  const [form, setForm] = useState({});

  useEffect(() => {
    const initial = {};
    action.schema.forEach((field) => {
      initial[field.name] = field.default ?? (field.type === "boolean" ? false : "");
    });
    if (preset?.actionId === action.id) {
      Object.assign(initial, preset.params || {});
    }
    setForm(initial);
  }, [action, preset]);

  return (
    <div className="stack">
      <div className="section-head">
        <div>
          <div className="eyebrow">{CATEGORY_META[action.category]?.label || action.category}</div>
          <h3>{action.label}</h3>
        </div>
        <span className="count-pill">{action.schema.length} campos</span>
      </div>
      <p>{action.description}</p>
      {action.dangerous ? <div className="warning-box">Acao sensivel. Revise os parametros antes de executar.</div> : null}
      <form className="stack" onSubmit={(event) => {
        event.preventDefault();
        onRunAction(action.id, form);
      }}>
        <div className="form-grid">
          {action.schema.map((field) => (
            <Field key={field.name} field={field} value={form[field.name]} onChange={(value) => setForm((current) => ({...current, [field.name]: value}))} />
          ))}
        </div>
        <button className="primary-button" type="submit" disabled={running}>{running ? "Enviando..." : "Executar automacao"}</button>
      </form>
    </div>
  );
}

function Field({field, value, onChange}) {
  if (field.type === "boolean") {
    return (
      <label className="toggle-field full-width-field">
        <div><strong>{field.label}</strong><small>Alterna este comportamento na execucao.</small></div>
        <input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />
      </label>
    );
  }
  if (field.type === "select") {
    return (
      <label>
        <span className="field-label">{field.label}</span>
        <select value={value} onChange={(event) => onChange(event.target.value)}>
          {(field.options || []).map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      </label>
    );
  }
  return (
    <label className={field.type === "textarea" ? "full-width-field" : ""}>
      <span className="field-label">{field.label}</span>
      {field.type === "textarea" ? (
        <textarea value={value || ""} onChange={(event) => onChange(event.target.value)} rows={4} />
      ) : (
        <input
          type={field.type === "password" ? "password" : field.type === "number" ? "number" : "text"}
          value={value ?? ""}
          onChange={(event) => onChange(field.type === "number" ? Number(event.target.value) : event.target.value)}
        />
      )}
    </label>
  );
}

function TasksPanel({tasks, selectedTask, onSelectTask}) {
  return (
    <div className="page-grid task-grid">
      <section className="panel-card">
        <div className="section-head"><div><div className="eyebrow">Fila</div><h3>Tarefas recentes</h3></div><span className="count-pill">{tasks.length}</span></div>
        <div className="action-list">
          {tasks.length ? tasks.map((task) => (
            <button key={task.id} className={selectedTask?.id === task.id ? "action-card active" : "action-card"} onClick={() => onSelectTask(task.id)}>
              <strong>{task.action}</strong>
              <small>{task.state}</small>
              <p>{task.message}</p>
            </button>
          )) : <div className="empty-box">Nenhuma tarefa enviada ainda.</div>}
        </div>
      </section>
      <section className="panel-card">
        {selectedTask ? (
          <div className="stack">
            <div className="section-head"><div><div className="eyebrow">Execucao</div><h3>{selectedTask.action}</h3></div><span className="count-pill">{selectedTask.progress || 0}%</span></div>
            <div className="stat-grid">
              <StatCard label="Estado" value={selectedTask.state} hint="status atual" tone="teal" />
              <StatCard label="Inicio" value={formatDate(selectedTask.startedAt)} hint="inicio da tarefa" tone="neutral" />
              <StatCard label="Fim" value={formatDate(selectedTask.finishedAt)} hint="quando finalizou" tone="ink" />
            </div>
            <div className="progress-bar"><div style={{width: `${selectedTask.progress || 0}%`}} /></div>
            <pre className="log-box">{pretty(selectedTask.result || (selectedTask.events || []))}</pre>
          </div>
        ) : <div className="empty-box">Selecione uma tarefa para ver detalhes.</div>}
      </section>
    </div>
  );
}

function AboutPanel({overview, actions}) {
  return (
    <div className="page-grid">
      <section className="panel-card">
        <div className="eyebrow">Plataforma</div>
        <h2>VpsToolsPy Admin Platform</h2>
        <p>Camada web para operar o script com mais contexto, menos friccao e mais capacidade de execucao.</p>
      </section>
      <section className="panel-card">
        <div className="section-head"><div><div className="eyebrow">Metadados</div><h3>Informacoes tecnicas</h3></div></div>
        <div className="table-like">
          <div className="list-row"><strong>Script version</strong><span>{overview?.panel?.scriptVersion || "-"}</span></div>
          <div className="list-row"><strong>Panel version</strong><span>{overview?.panel?.panelVersion || "-"}</span></div>
          <div className="list-row"><strong>Python</strong><span>{overview?.panel?.pythonCommand || "-"}</span></div>
          <div className="list-row"><strong>Acoes expostas</strong><span>{actions.length}</span></div>
        </div>
      </section>
    </div>
  );
}

export default App;
