import {useDeferredValue, useEffect, useMemo, useRef, useState} from "react";

const NAV_ITEMS = [
  {id: "overview", labelKey: "nav.overview.label", kickerKey: "nav.overview.kicker", icon: "home", tone: "blue"},
  {id: "operations", labelKey: "nav.operations.label", kickerKey: "nav.operations.kicker", icon: "bolt", tone: "green"},
  {id: "fleet", labelKey: "nav.fleet.label", kickerKey: "nav.fleet.kicker", icon: "dns", tone: "teal"},
  {id: "tasks", labelKey: "nav.tasks.label", kickerKey: "nav.tasks.kicker", icon: "schedule", tone: "amber"},
  {id: "about", labelKey: "nav.about.label", kickerKey: "nav.about.kicker", icon: "info", tone: "purple"}
];

const CATEGORY_META = {
  services: {labelKey: "category.services", icon: "dns", tone: "blue"},
  users: {labelKey: "category.users", icon: "groups", tone: "green"},
  database: {labelKey: "category.database", icon: "database", tone: "teal"},
  backend: {labelKey: "category.backend", icon: "terminal", tone: "purple"},
  infra: {labelKey: "category.infra", icon: "shield", tone: "amber"},
  panels: {labelKey: "category.panels", icon: "dashboard", tone: "blue"},
  system: {labelKey: "category.system", icon: "tune", tone: "teal"},
  dr: {labelKey: "category.dr", icon: "storage", tone: "purple"}
};

const HERO_ACTIONS = [
  {id: "panels.install_admin_web_panel", fallbackLabelKey: "hero.panel", icon: "dashboard", tone: "purple"},
  {id: "services.manage", fallbackLabelKey: "hero.services", icon: "dns", tone: "blue"},
  {id: "users.create", fallbackLabelKey: "hero.users", icon: "groups", tone: "green"},
  {id: "dr.run_backup", fallbackLabelKey: "hero.backups", icon: "storage", tone: "amber"},
  {id: "backend.prepare_spring_boot", fallbackLabelKey: "hero.backend", icon: "terminal", tone: "teal"}
];

const FLEET_SHORTCUT_ACTIONS = [
  "database.install_postgresql",
  "database.allow_postgresql_panel",
  "backend.prepare_spring_boot",
  "infra.configure_nginx",
  "infra.setup_https",
  "panels.install_web_db_panel",
  "panels.manage_web_db_panel",
  "panels.manage_admin_web_panel",
  "system.systemd_manage",
  "system.update_packages",
  "users.backup",
  "dr.run_monitor"
];

const SERVICE_CONTEXT_ACTIONS = {
  OPENCLAW: ["services.install_openclaw", "services.update_openclaw"],
  VNC: ["services.install_vnc", "services.change_vnc_port", "services.change_vnc_password", "services.configure_vnc_desktop"],
  OPENVPN: ["services.install_openvpn", "services.openvpn_add_client", "services.openvpn_revoke_client"]
};

const LANG_OPTIONS = [
  {id: "pt-BR", short: "PT", label: "Português"},
  {id: "en", short: "EN", label: "English"},
  {id: "es", short: "ES", label: "Español"}
];

const UI_TEXT = {
  "pt-BR": {
    "nav.overview.label": "Início",
    "nav.overview.kicker": "Visão central",
    "nav.operations.label": "Operações",
    "nav.operations.kicker": "Executar ações",
    "nav.fleet.label": "Infraestrutura",
    "nav.fleet.kicker": "Serviços e usuários",
    "nav.tasks.label": "Tarefas",
    "nav.tasks.kicker": "Fila e resultados",
    "nav.about.label": "Plataforma",
    "nav.about.kicker": "Versões e contexto",
    "category.services": "Serviços",
    "category.users": "Usuários",
    "category.database": "Banco",
    "category.backend": "Backend",
    "category.infra": "Infra",
    "category.panels": "Painéis",
    "category.system": "Sistema",
    "category.dr": "DR",
    "hero.panel": "Painel web",
    "hero.services": "Serviços",
    "hero.users": "Usuários SSH",
    "hero.backups": "Backups",
    "hero.backend": "Backend",
    "common.unknown": "Desconhecido",
    "common.none": "Nenhum",
    "common.loadingPlatform": "Carregando plataforma...",
    "common.loadingOverview": "Carregando visão geral...",
    "common.loadingInfra": "Carregando infraestrutura...",
    "common.noTasks": "Nenhuma tarefa enviada ainda.",
    "common.noActions": "Nenhuma automação disponível.",
    "common.language": "Idioma",
    "common.host": "Host",
    "common.user": "Usuário",
    "common.ip": "IP",
    "common.script": "Script",
    "common.logout": "Sair",
    "common.search": "Buscar ação, serviço ou domínio operacional",
    "common.searchCatalog": "Abrir catálogo",
    "common.searchActionCatalog": "Buscar ação, categoria ou descrição",
    "common.all": "Tudo",
    "common.selectTask": "Selecione uma tarefa para ver detalhes.",
    "common.fieldToggleHint": "Alterna este comportamento na execução.",
    "common.missingRequired": "Preencha os campos obrigatórios antes de executar.",
    "common.fieldRequired": "obrigatório",
    "common.sensitiveAction": "Ação sensível. Revise os parâmetros antes de executar.",
    "common.submitAction": "Executar automação",
    "common.submitting": "Enviando...",
    "common.loginTitle": "Centro operacional da VPS",
    "common.loginText": "Interface redesenhada para operar serviços, usuários SSH, banco, DR e tarefas em um fluxo mais claro.",
    "common.loginUser": "Usuário",
    "common.loginPassword": "Senha",
    "common.loginButton": "Entrar no painel",
    "common.loginLoading": "Entrando...",
    "common.invalidCredentials": "Credenciais inválidas.",
    "common.dashboardCenter": "Centro de controle",
    "common.help": "Ajuda",
    "common.apps": "Aplicativos",
    "common.account": "Conta",
    "common.operationalPlatform": "Plataforma operacional",
    "common.platformDescription": "Painel remodelado em linguagem Material 3 para operar a VPS com mais contexto.",
    "common.activeTasks": "Tarefas ativas",
    "common.recentFailures": "Falhas recentes",
    "common.controlCenterTitle": "Operação centralizada de serviços, usuários SSH, banco, backend e recuperação.",
    "common.managedServices": "Serviços gerenciados",
    "common.activeInstalled": "ativos / instalados",
    "common.sshUsers": "Usuários SSH",
    "common.connectedNow": "{count} conectados",
    "common.backups": "Backups",
    "common.healthyNow": "{count} saudáveis",
    "common.queue": "Fila operacional",
    "common.runningNow": "tarefas rodando",
    "common.success": "Sucesso",
    "common.error": "Erro",
    "common.close": "Fechar",
    "common.rawDetails": "Detalhes técnicos",
    "common.completedWithSuccess": "Tarefa concluída com sucesso.",
    "common.failedWithError": "A tarefa falhou.",
    "common.resultSummary": "Resumo do resultado",
    "common.noAdditionalDetails": "Nenhum detalhe adicional disponível.",
    "common.completedAt": "finalizada",
    "overview.assisted": "Operação assistida",
    "overview.actionCenters": "Centros de ação",
    "overview.adminPanel": "Painel administrativo",
    "overview.adminPanelDesc": "Instalação, rebuild e endurecimento do deploy.",
    "overview.mainDatabase": "Banco principal",
    "overview.mainDatabaseDesc": "Provisionamento do PostgreSQL e preparo de conexões.",
    "overview.backend": "Backend",
    "overview.backendDesc": "Runtime, variáveis de ambiente e padrão de execução.",
    "overview.system": "Sistema",
    "overview.systemDesc": "Atualizações, manutenção e limpeza operacional.",
    "overview.operationalHealth": "Saúde operacional",
    "overview.priorityServices": "Serviços prioritários",
    "overview.sshIdentity": "Identidade SSH",
    "overview.managedUsers": "Usuários gerenciados",
    "overview.expiresOn": "expira em {value}",
    "overview.limit": "limite {value}",
    "overview.online": "{count} online",
    "overview.disconnect": "Desconectar",
    "overview.backupsAndDr": "Backups e DR",
    "overview.resilience": "Postura de resiliência",
    "overview.run": "Executar",
    "overview.noBackupJobs": "Nenhum job de backup configurado.",
    "overview.recentQueue": "Fila recente",
    "overview.platformRuns": "Execuções da plataforma",
    "overview.noTaskMessage": "Sem mensagem adicional.",
    "fleet.operationalFleet": "Fleet operacional",
    "fleet.managedServices": "Serviços gerenciados",
    "fleet.users": "Usuários",
    "fleet.sshAdjustments": "Ajustes do SSH",
    "fleet.password": "Senha",
    "fleet.limit": "Limite",
    "fleet.recovery": "Recuperação",
    "fleet.drContext": "Contexto de DR",
    "fleet.drProfiles": "Perfis DR",
    "fleet.drMonitors": "Monitores DR",
    "fleet.backupJobs": "Jobs de backup",
    "fleet.exportConfigs": "Exportar configs",
    "fleet.restoreTest": "Teste de restore",
    "service.status": "Status",
    "service.restart": "Reiniciar",
    "service.start": "Iniciar",
    "service.stop": "Parar",
    "service.logs": "Logs",
    "service.noPorts": "sem portas",
    "service.compositePorts": "portas compostas",
    "operations.catalog": "Catálogo do script",
    "operations.available": "Automações disponíveis",
    "operations.tabCatalog": "Catálogo do script",
    "operations.tabCatalogDesc": "Automações disponíveis",
    "operations.tabServices": "Serviços",
    "operations.tabServicesDesc": "Operar serviço gerenciado",
    "operations.serviceGridTitle": "Serviços gerenciados",
    "operations.serviceGridCopy": "Abra a visão completa dos serviços, filtre mais rápido e execute ações diretamente dos cards.",
    "operations.serviceSearch": "Buscar serviço, família ou status",
    "operations.allFamilies": "Todas as famílias",
    "operations.noServices": "Nenhum serviço gerenciado disponível.",
    "operations.filtered": "{count} ações visíveis",
    "operations.selected": "Ação selecionada",
    "operations.pickAction": "Escolha uma ação",
    "operations.pickActionCopy": "Filtre por categoria ou busque pelo nome para abrir a automação certa mais rápido.",
    "tasks.queue": "Fila",
    "tasks.recent": "Tarefas recentes",
    "tasks.execution": "Execução",
    "tasks.state": "Estado",
    "tasks.start": "Início",
    "tasks.end": "Fim",
    "tasks.currentStatus": "status atual",
    "tasks.startHint": "início da tarefa",
    "tasks.endHint": "quando finalizou",
    "about.platform": "Plataforma",
    "about.adminPanel": "Painel administrativo",
    "about.platformCopy": "Interface web para operar o script com mais contexto visual, menos densidade desnecessária e melhor distribuição dos elementos.",
    "about.metadata": "Metadados",
    "about.technicalInfo": "Informações técnicas",
    "about.reading": "Leitura operacional",
    "about.notes": "Notas do painel",
    "about.scriptVersion": "Versão do script",
    "about.panelVersion": "Versão do painel",
    "about.python": "Python",
    "about.exposedActions": "Ações expostas",
    "about.material3": "Layout Material 3",
    "about.largeIcons": "Rail com ícones amplos",
    "about.cards": "Cards reposicionados",
    "about.centralSearch": "Busca centralizada",
    "about.taskFlow": "Fluxo orientado a tarefa"
  },
  "en": {
    "nav.overview.label": "Home",
    "nav.overview.kicker": "Central view",
    "nav.operations.label": "Operations",
    "nav.operations.kicker": "Run actions",
    "nav.fleet.label": "Infrastructure",
    "nav.fleet.kicker": "Services and users",
    "nav.tasks.label": "Tasks",
    "nav.tasks.kicker": "Queue and results",
    "nav.about.label": "Platform",
    "nav.about.kicker": "Versions and context",
    "category.services": "Services",
    "category.users": "Users",
    "category.database": "Database",
    "category.backend": "Backend",
    "category.infra": "Infra",
    "category.panels": "Panels",
    "category.system": "System",
    "category.dr": "DR",
    "hero.panel": "Web panel",
    "hero.services": "Services",
    "hero.users": "SSH users",
    "hero.backups": "Backups",
    "hero.backend": "Backend",
    "common.unknown": "Unknown",
    "common.none": "None",
    "common.loadingPlatform": "Loading platform...",
    "common.loadingOverview": "Loading overview...",
    "common.loadingInfra": "Loading infrastructure...",
    "common.noTasks": "No tasks submitted yet.",
    "common.noActions": "No automations available.",
    "common.language": "Language",
    "common.host": "Host",
    "common.user": "User",
    "common.ip": "IP",
    "common.script": "Script",
    "common.logout": "Log out",
    "common.search": "Search action, service or operational domain",
    "common.searchCatalog": "Open catalog",
    "common.searchActionCatalog": "Search action, category or description",
    "common.all": "All",
    "common.selectTask": "Select a task to see details.",
    "common.fieldToggleHint": "Toggle this behavior during execution.",
    "common.missingRequired": "Fill in the required fields before running.",
    "common.fieldRequired": "required",
    "common.sensitiveAction": "Sensitive action. Review the parameters before running it.",
    "common.submitAction": "Run automation",
    "common.submitting": "Submitting...",
    "common.loginTitle": "VPS operations center",
    "common.loginText": "Redesigned interface to operate services, SSH users, database, DR and tasks in a clearer flow.",
    "common.loginUser": "Username",
    "common.loginPassword": "Password",
    "common.loginButton": "Sign in",
    "common.loginLoading": "Signing in...",
    "common.invalidCredentials": "Invalid credentials.",
    "common.dashboardCenter": "Control center",
    "common.help": "Help",
    "common.apps": "Apps",
    "common.account": "Account",
    "common.operationalPlatform": "Operational platform",
    "common.platformDescription": "Material 3 dashboard redesigned to operate the VPS with more context.",
    "common.activeTasks": "Active tasks",
    "common.recentFailures": "Recent failures",
    "common.controlCenterTitle": "Centralized operation for services, SSH users, database, backend and recovery.",
    "common.managedServices": "Managed services",
    "common.activeInstalled": "active / installed",
    "common.sshUsers": "SSH users",
    "common.connectedNow": "{count} connected",
    "common.backups": "Backups",
    "common.healthyNow": "{count} healthy",
    "common.queue": "Operational queue",
    "common.runningNow": "tasks running",
    "common.success": "Success",
    "common.error": "Error",
    "common.close": "Close",
    "common.rawDetails": "Technical details",
    "common.completedWithSuccess": "Task completed successfully.",
    "common.failedWithError": "The task failed.",
    "common.resultSummary": "Result summary",
    "common.noAdditionalDetails": "No additional details available.",
    "common.completedAt": "finished",
    "overview.assisted": "Assisted operations",
    "overview.actionCenters": "Action centers",
    "overview.adminPanel": "Admin panel",
    "overview.adminPanelDesc": "Install, rebuild and harden the deployment.",
    "overview.mainDatabase": "Main database",
    "overview.mainDatabaseDesc": "Provision PostgreSQL and prepare connections.",
    "overview.backend": "Backend",
    "overview.backendDesc": "Runtime, environment variables and execution standard.",
    "overview.system": "System",
    "overview.systemDesc": "Updates, maintenance and operational cleanup.",
    "overview.operationalHealth": "Operational health",
    "overview.priorityServices": "Priority services",
    "overview.sshIdentity": "SSH identity",
    "overview.managedUsers": "Managed users",
    "overview.expiresOn": "expires on {value}",
    "overview.limit": "limit {value}",
    "overview.online": "{count} online",
    "overview.disconnect": "Disconnect",
    "overview.backupsAndDr": "Backups and DR",
    "overview.resilience": "Resilience posture",
    "overview.run": "Run",
    "overview.noBackupJobs": "No backup jobs configured.",
    "overview.recentQueue": "Recent queue",
    "overview.platformRuns": "Platform runs",
    "overview.noTaskMessage": "No additional message.",
    "fleet.operationalFleet": "Operational fleet",
    "fleet.managedServices": "Managed services",
    "fleet.users": "Users",
    "fleet.sshAdjustments": "SSH adjustments",
    "fleet.password": "Password",
    "fleet.limit": "Limit",
    "fleet.recovery": "Recovery",
    "fleet.drContext": "DR context",
    "fleet.drProfiles": "DR profiles",
    "fleet.drMonitors": "DR monitors",
    "fleet.backupJobs": "Backup jobs",
    "fleet.exportConfigs": "Export configs",
    "fleet.restoreTest": "Restore test",
    "service.status": "Status",
    "service.restart": "Restart",
    "service.start": "Start",
    "service.stop": "Stop",
    "service.logs": "Logs",
    "service.noPorts": "no ports",
    "service.compositePorts": "composite ports",
    "operations.catalog": "Script catalog",
    "operations.available": "Available automations",
    "operations.tabCatalog": "Script catalog",
    "operations.tabCatalogDesc": "Available automations",
    "operations.tabServices": "Services",
    "operations.tabServicesDesc": "Operate managed service",
    "operations.serviceGridTitle": "Managed services",
    "operations.serviceGridCopy": "Open the full service view, filter faster and run actions directly from the cards.",
    "operations.serviceSearch": "Search service, family or status",
    "operations.allFamilies": "All families",
    "operations.noServices": "No managed services available.",
    "operations.filtered": "{count} visible actions",
    "operations.selected": "Selected action",
    "operations.pickAction": "Choose an action",
    "operations.pickActionCopy": "Filter by category or search by name to open the right automation faster.",
    "tasks.queue": "Queue",
    "tasks.recent": "Recent tasks",
    "tasks.execution": "Execution",
    "tasks.state": "State",
    "tasks.start": "Start",
    "tasks.end": "End",
    "tasks.currentStatus": "current status",
    "tasks.startHint": "task start",
    "tasks.endHint": "when it finished",
    "about.platform": "Platform",
    "about.adminPanel": "Admin panel",
    "about.platformCopy": "Web interface to operate the script with more visual context, less unnecessary density and better element distribution.",
    "about.metadata": "Metadata",
    "about.technicalInfo": "Technical information",
    "about.reading": "Operational reading",
    "about.notes": "Panel notes",
    "about.scriptVersion": "Script version",
    "about.panelVersion": "Panel version",
    "about.python": "Python",
    "about.exposedActions": "Exposed actions",
    "about.material3": "Material 3 layout",
    "about.largeIcons": "Rail with larger icons",
    "about.cards": "Repositioned cards",
    "about.centralSearch": "Central search",
    "about.taskFlow": "Task-oriented flow"
  },
  "es": {
    "nav.overview.label": "Inicio",
    "nav.overview.kicker": "Vista central",
    "nav.operations.label": "Operaciones",
    "nav.operations.kicker": "Ejecutar acciones",
    "nav.fleet.label": "Infraestructura",
    "nav.fleet.kicker": "Servicios y usuarios",
    "nav.tasks.label": "Tareas",
    "nav.tasks.kicker": "Cola y resultados",
    "nav.about.label": "Plataforma",
    "nav.about.kicker": "Versiones y contexto",
    "category.services": "Servicios",
    "category.users": "Usuarios",
    "category.database": "Base de datos",
    "category.backend": "Backend",
    "category.infra": "Infra",
    "category.panels": "Paneles",
    "category.system": "Sistema",
    "category.dr": "DR",
    "hero.panel": "Panel web",
    "hero.services": "Servicios",
    "hero.users": "Usuarios SSH",
    "hero.backups": "Respaldos",
    "hero.backend": "Backend",
    "common.unknown": "Desconocido",
    "common.none": "Ninguno",
    "common.loadingPlatform": "Cargando plataforma...",
    "common.loadingOverview": "Cargando vista general...",
    "common.loadingInfra": "Cargando infraestructura...",
    "common.noTasks": "Todavía no se enviaron tareas.",
    "common.noActions": "No hay automatizaciones disponibles.",
    "common.language": "Idioma",
    "common.host": "Host",
    "common.user": "Usuario",
    "common.ip": "IP",
    "common.script": "Script",
    "common.logout": "Salir",
    "common.search": "Buscar acción, servicio o dominio operativo",
    "common.searchCatalog": "Abrir catálogo",
    "common.searchActionCatalog": "Buscar acción, categoría o descripción",
    "common.all": "Todo",
    "common.selectTask": "Seleccione una tarea para ver detalles.",
    "common.fieldToggleHint": "Activa este comportamiento durante la ejecución.",
    "common.missingRequired": "Complete los campos obligatorios antes de ejecutar.",
    "common.fieldRequired": "obligatorio",
    "common.sensitiveAction": "Acción sensible. Revise los parámetros antes de ejecutarla.",
    "common.submitAction": "Ejecutar automatización",
    "common.submitting": "Enviando...",
    "common.loginTitle": "Centro operativo de la VPS",
    "common.loginText": "Interfaz rediseñada para operar servicios, usuarios SSH, base de datos, DR y tareas en un flujo más claro.",
    "common.loginUser": "Usuario",
    "common.loginPassword": "Contraseña",
    "common.loginButton": "Entrar al panel",
    "common.loginLoading": "Entrando...",
    "common.invalidCredentials": "Credenciales inválidas.",
    "common.dashboardCenter": "Centro de control",
    "common.help": "Ayuda",
    "common.apps": "Aplicaciones",
    "common.account": "Cuenta",
    "common.operationalPlatform": "Plataforma operativa",
    "common.platformDescription": "Panel Material 3 rediseñado para operar la VPS con más contexto.",
    "common.activeTasks": "Tareas activas",
    "common.recentFailures": "Fallos recientes",
    "common.controlCenterTitle": "Operación centralizada de servicios, usuarios SSH, base de datos, backend y recuperación.",
    "common.managedServices": "Servicios gestionados",
    "common.activeInstalled": "activos / instalados",
    "common.sshUsers": "Usuarios SSH",
    "common.connectedNow": "{count} conectados",
    "common.backups": "Respaldos",
    "common.healthyNow": "{count} saludables",
    "common.queue": "Cola operativa",
    "common.runningNow": "tareas en ejecución",
    "common.success": "Éxito",
    "common.error": "Error",
    "common.close": "Cerrar",
    "common.rawDetails": "Detalles técnicos",
    "common.completedWithSuccess": "La tarea se completó con éxito.",
    "common.failedWithError": "La tarea falló.",
    "common.resultSummary": "Resumen del resultado",
    "common.noAdditionalDetails": "No hay detalles adicionales disponibles.",
    "common.completedAt": "finalizada",
    "overview.assisted": "Operación asistida",
    "overview.actionCenters": "Centros de acción",
    "overview.adminPanel": "Panel administrativo",
    "overview.adminPanelDesc": "Instalación, rebuild y endurecimiento del despliegue.",
    "overview.mainDatabase": "Base principal",
    "overview.mainDatabaseDesc": "Provisionamiento de PostgreSQL y preparación de conexiones.",
    "overview.backend": "Backend",
    "overview.backendDesc": "Runtime, variables de entorno y estándar de ejecución.",
    "overview.system": "Sistema",
    "overview.systemDesc": "Actualizaciones, mantenimiento y limpieza operativa.",
    "overview.operationalHealth": "Salud operativa",
    "overview.priorityServices": "Servicios prioritarios",
    "overview.sshIdentity": "Identidad SSH",
    "overview.managedUsers": "Usuarios gestionados",
    "overview.expiresOn": "vence en {value}",
    "overview.limit": "límite {value}",
    "overview.online": "{count} en línea",
    "overview.disconnect": "Desconectar",
    "overview.backupsAndDr": "Respaldos y DR",
    "overview.resilience": "Postura de resiliencia",
    "overview.run": "Ejecutar",
    "overview.noBackupJobs": "No hay trabajos de respaldo configurados.",
    "overview.recentQueue": "Cola reciente",
    "overview.platformRuns": "Ejecuciones de la plataforma",
    "overview.noTaskMessage": "Sin mensaje adicional.",
    "fleet.operationalFleet": "Fleet operativa",
    "fleet.managedServices": "Servicios gestionados",
    "fleet.users": "Usuarios",
    "fleet.sshAdjustments": "Ajustes de SSH",
    "fleet.password": "Contraseña",
    "fleet.limit": "Límite",
    "fleet.recovery": "Recuperación",
    "fleet.drContext": "Contexto DR",
    "fleet.drProfiles": "Perfiles DR",
    "fleet.drMonitors": "Monitores DR",
    "fleet.backupJobs": "Trabajos de respaldo",
    "fleet.exportConfigs": "Exportar configs",
    "fleet.restoreTest": "Prueba de restore",
    "service.status": "Estado",
    "service.restart": "Reiniciar",
    "service.start": "Iniciar",
    "service.stop": "Detener",
    "service.logs": "Logs",
    "service.noPorts": "sin puertos",
    "service.compositePorts": "puertos compuestos",
    "operations.catalog": "Catálogo del script",
    "operations.available": "Automatizaciones disponibles",
    "operations.tabCatalog": "Catálogo del script",
    "operations.tabCatalogDesc": "Automatizaciones disponibles",
    "operations.tabServices": "Servicios",
    "operations.tabServicesDesc": "Operar servicio gestionado",
    "operations.serviceGridTitle": "Servicios gestionados",
    "operations.serviceGridCopy": "Abra la vista completa de los servicios, filtre más rápido y ejecute acciones directamente desde las tarjetas.",
    "operations.serviceSearch": "Buscar servicio, familia o estado",
    "operations.allFamilies": "Todas las familias",
    "operations.noServices": "No hay servicios gestionados disponibles.",
    "operations.filtered": "{count} acciones visibles",
    "operations.selected": "Acción seleccionada",
    "operations.pickAction": "Elija una acción",
    "operations.pickActionCopy": "Filtre por categoría o busque por nombre para abrir la automatización correcta más rápido.",
    "tasks.queue": "Cola",
    "tasks.recent": "Tareas recientes",
    "tasks.execution": "Ejecución",
    "tasks.state": "Estado",
    "tasks.start": "Inicio",
    "tasks.end": "Fin",
    "tasks.currentStatus": "estado actual",
    "tasks.startHint": "inicio de la tarea",
    "tasks.endHint": "cuando terminó",
    "about.platform": "Plataforma",
    "about.adminPanel": "Panel administrativo",
    "about.platformCopy": "Interfaz web para operar el script con más contexto visual, menos densidad innecesaria y mejor distribución de los elementos.",
    "about.metadata": "Metadatos",
    "about.technicalInfo": "Información técnica",
    "about.reading": "Lectura operativa",
    "about.notes": "Notas del panel",
    "about.scriptVersion": "Versión del script",
    "about.panelVersion": "Versión del panel",
    "about.python": "Python",
    "about.exposedActions": "Acciones expuestas",
    "about.material3": "Layout Material 3",
    "about.largeIcons": "Rail con iconos amplios",
    "about.cards": "Cards reposicionados",
    "about.centralSearch": "Búsqueda central",
    "about.taskFlow": "Flujo orientado a tareas"
  }
};

const VALUE_TEXT = {
  "pt-BR": {
    unknown: "Desconhecido",
    not_installed: "Não instalado",
    installed: "Instalado",
    active: "Ativo",
    inactive: "Inativo",
    running: "Em execução",
    completed: "Concluída",
    failed: "Falhou",
    queued: "Na fila",
    success: "Sucesso",
    error: "Erro",
    healthy: "Saudável",
    unhealthy: "Com problema",
    enabled: "Habilitado",
    disabled: "Desabilitado",
    starting: "Iniciando",
    stopping: "Parando",
    stopped: "Parado",
    online: "Online",
    offline: "Offline",
    ok: "OK"
  },
  en: {
    unknown: "Unknown",
    not_installed: "Not installed",
    installed: "Installed",
    active: "Active",
    inactive: "Inactive",
    running: "Running",
    completed: "Completed",
    failed: "Failed",
    queued: "Queued",
    success: "Success",
    error: "Error",
    healthy: "Healthy",
    unhealthy: "Unhealthy",
    enabled: "Enabled",
    disabled: "Disabled",
    starting: "Starting",
    stopping: "Stopping",
    stopped: "Stopped",
    online: "Online",
    offline: "Offline",
    ok: "OK"
  },
  es: {
    unknown: "Desconocido",
    not_installed: "No instalado",
    installed: "Instalado",
    active: "Activo",
    inactive: "Inactivo",
    running: "En ejecución",
    completed: "Completada",
    failed: "Falló",
    queued: "En cola",
    success: "Éxito",
    error: "Error",
    healthy: "Saludable",
    unhealthy: "Con problema",
    enabled: "Habilitado",
    disabled: "Deshabilitado",
    starting: "Iniciando",
    stopping: "Deteniendo",
    stopped: "Detenido",
    online: "En línea",
    offline: "Fuera de línea",
    ok: "OK"
  }
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

function getInitialLocale() {
  if (typeof window === "undefined") {
    return "pt-BR";
  }
  const saved = window.localStorage.getItem("vps-tools-panel-locale");
  if (LANG_OPTIONS.some((item) => item.id === saved)) {
    return saved;
  }
  return "pt-BR";
}

function translate(locale, key, vars = {}) {
  const source = UI_TEXT[locale] || UI_TEXT["pt-BR"];
  const fallback = UI_TEXT["pt-BR"];
  let value = source[key] || fallback[key] || key;
  Object.entries(vars).forEach(([name, replacement]) => {
    value = value.replaceAll(`{${name}}`, String(replacement));
  });
  return value;
}

function formatDate(value, locale) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat(locale || "pt-BR", {
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

function capitalize(value) {
  if (!value) {
    return "-";
  }
  return String(value).charAt(0).toUpperCase() + String(value).slice(1);
}

function humanizeToken(value, locale, fallback = "-") {
  if (value == null || value === "") {
    return fallback;
  }
  if (typeof value !== "string") {
    return String(value);
  }
  const normalized = value.trim().toLowerCase();
  const translated = VALUE_TEXT[locale]?.[normalized] || VALUE_TEXT["pt-BR"]?.[normalized];
  if (translated) {
    return translated;
  }
  if (!/[_-]/.test(value)) {
    return value;
  }
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => {
      const token = VALUE_TEXT[locale]?.[part.toLowerCase()] || VALUE_TEXT["pt-BR"]?.[part.toLowerCase()];
      return token || capitalize(part);
    })
    .join(" ");
}

function getCategoryMeta(category, locale) {
  const meta = CATEGORY_META[category] || {labelKey: "", icon: "dashboard", tone: "blue"};
  return {
    ...meta,
    label: meta.labelKey ? translate(locale, meta.labelKey) : humanizeToken(category, locale)
  };
}

function getActionLabel(action, locale) {
  if (!action) {
    return "-";
  }
  return humanizeToken(action.label || action.id, locale);
}

function getActionDescription(action) {
  if (!action) {
    return "-";
  }
  return action.description || "-";
}

function getTaskLabel(taskAction, actionsById, locale) {
  const action = actionsById[taskAction];
  return action ? getActionLabel(action, locale) : humanizeToken(taskAction, locale);
}

function staggerStyle(index, start = 0, step = 70) {
  return {animationDelay: `${start + (index * step)}ms`};
}

function extractResultMessage(result, fallback) {
  if (!result) {
    return fallback;
  }
  if (typeof result === "string") {
    return result;
  }
  if (typeof result.message === "string" && result.message.trim()) {
    return result.message;
  }
  if (typeof result.error === "string" && result.error.trim()) {
    return result.error;
  }
  return fallback;
}

function summarizeServiceDetails(service, locale, t) {
  if (!service) {
    return "-";
  }
  const details = service.details;
  if (!details || typeof details !== "object") {
    return humanizeToken(details, locale, service.family || "-");
  }
  if (details.version && String(details.version).trim()) {
    return `v${details.version}`;
  }
  if (details.units && String(details.units).trim() && details.units !== "-") {
    return String(details.units);
  }
  if (details.status && String(details.status).trim()) {
    return humanizeToken(details.status, locale, service.family || "-");
  }
  return service.family || t("common.none");
}

function summarizeTaskResult(task, t) {
  if (!task) {
    return "-";
  }
  return extractResultMessage(task.result, task.message || t("overview.noTaskMessage"));
}

function normalizeActionParams(action, form) {
  const next = {};
  (action?.schema || []).forEach((field) => {
    const raw = form?.[field.name];
    if (field.type === "number") {
      if (raw === "" || raw == null) {
        next[field.name] = "";
      } else {
        next[field.name] = Number(raw);
      }
      return;
    }
    if (typeof raw === "string") {
      next[field.name] = raw.trim();
      return;
    }
    next[field.name] = raw;
  });
  return next;
}

function validateActionForm(action, form) {
  const normalized = normalizeActionParams(action, form);
  const missing = (action?.schema || []).filter((field) => {
    if (!field.required) {
      return false;
    }
    const value = normalized[field.name];
    if (field.type === "boolean") {
      return value == null;
    }
    if (field.type === "number") {
      return value === "" || Number.isNaN(value);
    }
    return value == null || value === "";
  });
  return {
    normalized,
    missing
  };
}

function getServiceContextActions(service, actionsById) {
  return (SERVICE_CONTEXT_ACTIONS[service?.key] || [])
    .map((actionId) => actionsById[actionId])
    .filter(Boolean);
}

function Icon({name}) {
  const common = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "1.9",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": "true"
  };

  switch (name) {
    case "home":
      return <svg {...common}><path d="M4 10.5 12 4l8 6.5" /><path d="M6.5 9.5V20h11V9.5" /><path d="M10 20v-5h4v5" /></svg>;
    case "bolt":
      return <svg {...common}><path d="M13 2 5 13h5l-1 9 8-11h-5z" /></svg>;
    case "dns":
      return <svg {...common}><rect x="4" y="5" width="16" height="5" rx="2" /><rect x="4" y="14" width="16" height="5" rx="2" /><path d="M8 7.5h.01M8 16.5h.01" /></svg>;
    case "schedule":
      return <svg {...common}><circle cx="12" cy="13" r="8" /><path d="M12 8v5l3 2" /><path d="M9 2h6" /></svg>;
    case "info":
      return <svg {...common}><circle cx="12" cy="12" r="9" /><path d="M12 10v6" /><path d="M12 7h.01" /></svg>;
    case "dashboard":
      return <svg {...common}><rect x="4" y="4" width="7" height="7" rx="2" /><rect x="13" y="4" width="7" height="11" rx="2" /><rect x="4" y="13" width="7" height="7" rx="2" /><rect x="13" y="17" width="7" height="3" rx="1.5" /></svg>;
    case "groups":
      return <svg {...common}><circle cx="9" cy="9" r="3" /><path d="M3.5 19a5.5 5.5 0 0 1 11 0" /><path d="M16 10.2a3 3 0 1 0 0-2.4" /><path d="M16.6 19a4.6 4.6 0 0 1 3.9-2.2" /></svg>;
    case "database":
      return <svg {...common}><ellipse cx="12" cy="6.5" rx="6.5" ry="3.5" /><path d="M5.5 6.5v11c0 1.9 2.9 3.5 6.5 3.5s6.5-1.6 6.5-3.5v-11" /><path d="M5.5 12c0 1.9 2.9 3.5 6.5 3.5s6.5-1.6 6.5-3.5" /></svg>;
    case "terminal":
      return <svg {...common}><rect x="3.5" y="5" width="17" height="14" rx="3" /><path d="m7 10 2.5 2.5L7 15" /><path d="M12 15h5" /></svg>;
    case "shield":
      return <svg {...common}><path d="M12 3.5 5.5 6v5.7c0 4.2 2.7 7.9 6.5 8.8 3.8-.9 6.5-4.6 6.5-8.8V6z" /><path d="m9.3 12 1.8 1.8 3.6-3.6" /></svg>;
    case "storage":
      return <svg {...common}><path d="M4.5 7.5h15" /><path d="M4.5 12h15" /><path d="M4.5 16.5h15" /><rect x="4" y="4" width="16" height="16" rx="3" /></svg>;
    case "search":
      return <svg {...common}><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4 4" /></svg>;
    case "logout":
      return <svg {...common}><path d="M10 4H6.5A2.5 2.5 0 0 0 4 6.5v11A2.5 2.5 0 0 0 6.5 20H10" /><path d="m14 16 4-4-4-4" /><path d="M8 12h10" /></svg>;
    case "help":
      return <svg {...common}><circle cx="12" cy="12" r="9" /><path d="M9.7 9.4a2.6 2.6 0 0 1 5 .9c0 1.9-2.1 2.3-2.7 3.6" /><path d="M12 17.2h.01" /></svg>;
    case "apps":
      return <svg {...common}><path d="M7 7h.01M12 7h.01M17 7h.01M7 12h.01M12 12h.01M17 12h.01M7 17h.01M12 17h.01M17 17h.01" /><path d="M7 7h0M12 7h0M17 7h0M7 12h0M12 12h0M17 12h0M7 17h0M12 17h0M17 17h0" strokeWidth="3.5" /></svg>;
    case "account":
      return <svg {...common}><circle cx="12" cy="8.2" r="3.2" /><path d="M5 19a7 7 0 0 1 14 0" /></svg>;
    case "tune":
      return <svg {...common}><path d="M4 6h8" /><path d="M16 6h4" /><path d="M4 12h4" /><path d="M12 12h8" /><path d="M4 18h10" /><path d="M18 18h2" /><circle cx="14" cy="6" r="2" /><circle cx="10" cy="12" r="2" /><circle cx="16" cy="18" r="2" /></svg>;
    default:
      return <svg {...common}><circle cx="12" cy="12" r="9" /></svg>;
  }
}

function LanguageSwitcher({locale, onChange, compact = false}) {
  return (
    <div className={compact ? "language-switcher compact" : "language-switcher"} aria-label="language-switcher">
      {LANG_OPTIONS.map((item) => (
        <button
          key={item.id}
          type="button"
          className={locale === item.id ? "lang-button active" : "lang-button"}
          onClick={() => onChange(item.id)}
          title={item.label}
        >
          {compact ? item.short : item.label}
        </button>
      ))}
    </div>
  );
}

function LoginForm({onLogin, loading, error, locale, onLocaleChange, t}) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");

  return (
    <div className="login-shell">
      <div className="login-card surface-card">
        <div className="login-toolbar">
          <span className="section-kicker">{t("common.language")}</span>
          <LanguageSwitcher locale={locale} onChange={onLocaleChange} compact />
        </div>
        <div className="section-kicker">VpsToolsPy Platform</div>
        <h1>{t("common.loginTitle")}</h1>
        <p className="body-copy">
          {t("common.loginText")}
        </p>
        <form
          className="stack-lg"
          onSubmit={(event) => {
            event.preventDefault();
            onLogin({username, password});
          }}
        >
          <label className="input-field">
            <span>{t("common.loginUser")}</span>
            <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
          </label>
          <label className="input-field">
            <span>{t("common.loginPassword")}</span>
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
          </label>
          {error ? <div className="support-banner danger">{error}</div> : null}
          <button className="filled-button" type="submit" disabled={loading}>
            {loading ? t("common.loginLoading") : t("common.loginButton")}
          </button>
        </form>
      </div>
    </div>
  );
}

function App() {
  const [locale, setLocale] = useState(getInitialLocale);
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
  const [heroSearch, setHeroSearch] = useState("");
  const [operationSearchSeed, setOperationSearchSeed] = useState({value: "", nonce: 0});
  const [snackbar, setSnackbar] = useState(null);
  const [errorDialog, setErrorDialog] = useState(null);
  const eventSources = useRef({});

  const selectedTask = useMemo(
    () => tasks.find((task) => task.id === selectedTaskId) || tasks[0] || null,
    [selectedTaskId, tasks]
  );
  const t = (key, vars) => translate(locale, key, vars);
  const navItems = useMemo(
    () => NAV_ITEMS.map((item) => ({...item, label: t(item.labelKey), kicker: t(item.kickerKey)})),
    [locale]
  );
  const heroActions = useMemo(
    () => HERO_ACTIONS.map((item) => ({...item, fallbackLabel: t(item.fallbackLabelKey)})),
    [locale]
  );
  const actionsById = useMemo(
    () => Object.fromEntries(actions.map((action) => [action.id, action])),
    [actions]
  );

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem("vps-tools-panel-locale", locale);
    }
  }, [locale]);

  useEffect(() => {
    if (!snackbar) {
      return undefined;
    }
    const timeout = window.setTimeout(() => setSnackbar(null), 4200);
    return () => window.clearTimeout(timeout);
  }, [snackbar]);

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
            if (payload.ok) {
              setSnackbar({
                title: t("common.success"),
                message: extractResultMessage(payload.data, t("common.completedWithSuccess"))
              });
            } else {
              setErrorDialog({
                title: t("common.error"),
                message: extractResultMessage(payload.data, t("common.failedWithError")),
                details: payload.data
              });
            }
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
      setLoginError(t("common.invalidCredentials"));
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
    const action = actionsById[actionId];
    const {normalized} = validateActionForm(action, formData);
    if (submittingAction) {
      return null;
    }
    try {
      setSubmittingAction(actionId);
      setAppError("");
      const task = await apiFetch("/api/tasks", {
        method: "POST",
        body: JSON.stringify({action: actionId, params: normalized})
      });
      setTasks((current) => [task, ...current]);
      setSelectedTaskId(task.id);
      setActiveTab(nextTab);
      return task;
    } catch (error) {
      setAppError(error.message || "Falha ao enviar automacao.");
      setErrorDialog({
        title: t("common.error"),
        message: error.message || t("common.failedWithError"),
        details: null
      });
      throw error;
    } finally {
      setSubmittingAction("");
    }
  };

  const openAction = (actionId, params = {}) => {
    setActionPreset({actionId, params, nonce: Date.now()});
    setActiveTab("operations");
  };

  const submitHeroSearch = (event) => {
    event.preventDefault();
    setActiveTab("operations");
    setOperationSearchSeed({value: heroSearch.trim(), nonce: Date.now()});
  };

  if (loadingAuth) {
    return <div className="loading-screen">{t("common.loadingPlatform")}</div>;
  }

  if (!auth.authenticated) {
    return <LoginForm onLogin={handleLogin} loading={loadingAuth} error={loginError} locale={locale} onLocaleChange={setLocale} t={t} />;
  }

  const data = overview?.overview;
  const runningTasks = tasks.filter((task) => task.state === "running").length;
  const failedTasks = tasks.filter((task) => task.state === "failed").length;

  return (
    <div className="app-shell">
      <aside className="rail">
        <div className="rail-brand">
          <div className="brand-badge">VP</div>
          <div>
            <div className="section-kicker">Plataforma operacional</div>
            <h2>VpsToolsPy</h2>
            <p className="muted-copy">
              {t("common.platformDescription")}
            </p>
          </div>
        </div>

        <nav className="rail-nav">
          {navItems.map((tab, index) => (
            <button
              key={tab.id}
              className={activeTab === tab.id ? "rail-item active" : "rail-item"}
              onClick={() => setActiveTab(tab.id)}
              style={staggerStyle(index, 60, 55)}
            >
              <span className={`nav-icon nav-icon-${tab.tone}`}>
                <Icon name={tab.icon} />
              </span>
              <span className="rail-item-copy">
                <strong>{tab.label}</strong>
                <small>{tab.kicker}</small>
              </span>
            </button>
          ))}
        </nav>

        <div className="surface-card rail-summary">
          <div className="summary-row">
            <span>{t("common.user")}</span>
            <strong>{auth.username}</strong>
          </div>
          <div className="summary-row">
            <span>{t("common.activeTasks")}</span>
            <strong>{runningTasks}</strong>
          </div>
          <div className="summary-row">
            <span>{t("common.recentFailures")}</span>
            <strong>{failedTasks}</strong>
          </div>
          <div className="summary-row">
            <span>{t("common.host")}</span>
            <strong>{data?.script?.hostname || t("common.unknown")}</strong>
          </div>
          <button className="tonal-button logout-button" onClick={handleLogout}>
            <Icon name="logout" />
            {t("common.logout")}
          </button>
        </div>
      </aside>

      <main className="workspace">
        <header className="workspace-topbar">
          <div>
            <div className="section-kicker">{t("common.dashboardCenter")}</div>
            <h1>{navItems.find((tab) => tab.id === activeTab)?.label || t("nav.about.label")}</h1>
          </div>
          <div className="top-actions">
            <LanguageSwitcher locale={locale} onChange={setLocale} />
            <button className="icon-button" type="button" aria-label={t("common.help")}>
              <Icon name="help" />
            </button>
            <button className="icon-button" type="button" aria-label={t("common.apps")}>
              <Icon name="apps" />
            </button>
            <button className="icon-button account-button" type="button" aria-label={t("common.account")}>
              <Icon name="account" />
            </button>
          </div>
        </header>

        {activeTab === "overview" ? (
          <section className="surface-card account-stage">
            <div className="account-identity">
              <div className="account-avatar">VP</div>
              <div>
                <h2>{data?.script?.hostname || "VpsToolsPy Control Center"}</h2>
                <p className="body-copy">
                  {t("common.controlCenterTitle")}
                </p>
                <div className="identity-pills">
                  <span className="support-pill">{t("common.host")} {data?.script?.hostname || t("common.unknown")}</span>
                  <span className="support-pill">{t("common.ip")} {data?.script?.public_ip || t("common.none")}</span>
                  <span className="support-pill">{t("common.script")} {overview?.panel?.scriptVersion || t("common.unknown")}</span>
                </div>
              </div>
            </div>

            <form className="search-stage" onSubmit={submitHeroSearch}>
              <div className="search-field">
                <Icon name="search" />
                <input
                  value={heroSearch}
                  onChange={(event) => setHeroSearch(event.target.value)}
                  placeholder={t("common.search")}
                />
              </div>
              <button className="filled-button" type="submit">{t("common.searchCatalog")}</button>
            </form>

            <div className="suggestion-row">
              {heroActions.map((item, index) => {
                const action = actions.find((entry) => entry.id === item.id);
                return (
                  <button
                    key={item.id}
                    className="suggestion-chip"
                    type="button"
                    onClick={() => openAction(item.id)}
                    style={staggerStyle(index, 120, 50)}
                  >
                    <span className={`chip-icon chip-icon-${item.tone}`}>
                      <Icon name={item.icon} />
                    </span>
                    {action ? getActionLabel(action, locale) : item.fallbackLabel}
                  </button>
                );
              })}
            </div>

            <div className="hero-stat-grid">
              <HeroStat
                icon="dns"
                tone="blue"
                label={t("common.managedServices")}
                value={`${data?.highlights?.managed_services_active || 0}/${data?.highlights?.managed_services_installed || 0}`}
                hint={t("common.activeInstalled")}
                index={0}
              />
              <HeroStat
                icon="groups"
                tone="green"
                label={t("common.sshUsers")}
                value={String(data?.users?.count || 0)}
                hint={t("common.connectedNow", {count: data?.users?.connected_count || 0})}
                index={1}
              />
              <HeroStat
                icon="storage"
                tone="amber"
                label={t("common.backups")}
                value={String(data?.backups?.count || 0)}
                hint={t("common.healthyNow", {count: data?.backups?.healthy_count || 0})}
                index={2}
              />
              <HeroStat
                icon="schedule"
                tone="purple"
                label={t("common.queue")}
                value={String(runningTasks)}
                hint={t("common.runningNow")}
                index={3}
              />
            </div>
          </section>
        ) : null}

        {appError ? <div className="support-banner danger">{appError}</div> : null}

        {activeTab === "overview" ? (
          <OverviewPanel overview={overview} tasks={tasks} onQuickRun={handleRunAction} onOpenAction={openAction} t={t} locale={locale} actionsById={actionsById} />
        ) : null}
        {activeTab === "operations" ? (
          <OperationsPanel
            actions={actions}
            overview={overview}
            actionsById={actionsById}
            runningAction={submittingAction}
            onRunAction={handleRunAction}
            onOpenAction={openAction}
            preset={actionPreset}
            searchSeed={operationSearchSeed}
            t={t}
            locale={locale}
          />
        ) : null}
        {activeTab === "fleet" ? (
          <FleetPanel overview={overview} actionsById={actionsById} onQuickRun={handleRunAction} onOpenAction={openAction} t={t} locale={locale} />
        ) : null}
        {activeTab === "tasks" ? (
          <TasksPanel tasks={tasks} selectedTask={selectedTask} onSelectTask={setSelectedTaskId} t={t} locale={locale} actionsById={actionsById} />
        ) : null}
        {activeTab === "about" ? <AboutPanel overview={overview} actions={actions} t={t} /> : null}
      </main>

      {snackbar ? (
        <div className="snackbar" role="status" aria-live="polite">
          <strong>{snackbar.title}</strong>
          <span>{snackbar.message}</span>
        </div>
      ) : null}

      {errorDialog ? (
        <div className="dialog-backdrop" role="presentation" onClick={() => setErrorDialog(null)}>
          <div className="dialog-card" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="section-header">
              <div>
                <div className="section-kicker">{t("common.error")}</div>
                <h3>{errorDialog.title}</h3>
              </div>
            </div>
            <p className="body-copy">{errorDialog.message}</p>
            {errorDialog.details ? (
              <details className="raw-details">
                <summary>{t("common.rawDetails")}</summary>
                <pre className="log-panel compact">{pretty(errorDialog.details)}</pre>
              </details>
            ) : null}
            <div className="dialog-actions">
              <button className="filled-button" type="button" onClick={() => setErrorDialog(null)}>{t("common.close")}</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function HeroStat({icon, tone, label, value, hint, index = 0}) {
  return (
    <div className="hero-stat-card motion-rise" style={staggerStyle(index, 150, 65)}>
      <span className={`chip-icon chip-icon-${tone}`}>
        <Icon name={icon} />
      </span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
        <span>{hint}</span>
      </div>
    </div>
  );
}

function SectionHeader({kicker, title, value}) {
  return (
    <div className="section-header">
      <div>
        <div className="section-kicker">{kicker}</div>
        <h3>{title}</h3>
      </div>
      {value != null ? <span className="support-pill strong">{value}</span> : null}
    </div>
  );
}

function OverviewPanel({overview, tasks, onQuickRun, onOpenAction, t, locale, actionsById}) {
  if (!overview) {
    return <div className="surface-card">{t("common.loadingOverview")}</div>;
  }

  const data = overview.overview;
  const topServices = (data.managed_services || []).slice(0, 6);
  const topUsers = (data.users?.items || []).slice(0, 5);
  const topJobs = (data.backups?.items || []).slice(0, 4);
  const topTasks = tasks.slice(0, 4);

  return (
    <div className="page-grid">
      <section className="dashboard-grid">
        <div className="surface-card feature-card">
          <SectionHeader kicker={t("overview.assisted")} title={t("overview.actionCenters")} />
          <div className="feature-action-grid">
            <button className="feature-action motion-rise" style={staggerStyle(0, 90, 60)} onClick={() => onOpenAction("panels.install_admin_web_panel")}>
              <span className="chip-icon chip-icon-purple"><Icon name="dashboard" /></span>
              <div>
                <strong>{t("overview.adminPanel")}</strong>
                <p>{t("overview.adminPanelDesc")}</p>
              </div>
            </button>
            <button className="feature-action motion-rise" style={staggerStyle(1, 90, 60)} onClick={() => onOpenAction("database.install_postgresql")}>
              <span className="chip-icon chip-icon-teal"><Icon name="database" /></span>
              <div>
                <strong>{t("overview.mainDatabase")}</strong>
                <p>{t("overview.mainDatabaseDesc")}</p>
              </div>
            </button>
            <button className="feature-action motion-rise" style={staggerStyle(2, 90, 60)} onClick={() => onOpenAction("backend.prepare_spring_boot")}>
              <span className="chip-icon chip-icon-blue"><Icon name="terminal" /></span>
              <div>
                <strong>{t("overview.backend")}</strong>
                <p>{t("overview.backendDesc")}</p>
              </div>
            </button>
            <button className="feature-action motion-rise" style={staggerStyle(3, 90, 60)} onClick={() => onOpenAction("system.update_packages")}>
              <span className="chip-icon chip-icon-amber"><Icon name="tune" /></span>
              <div>
                <strong>{t("overview.system")}</strong>
                <p>{t("overview.systemDesc")}</p>
              </div>
            </button>
          </div>
        </div>

        <div className="surface-card compact-card">
          <SectionHeader kicker={t("overview.operationalHealth")} title={t("overview.priorityServices")} value={topServices.length} />
          <div className="service-stack">
            {topServices.map((service, index) => (
              <article className="service-row-card motion-rise" style={staggerStyle(index, 120, 50)} key={service.key}>
                <div className="service-row-copy">
                  <div className="row-title">
                    <strong>{service.name}</strong>
                    <span className={service.active ? "state-pill state-ok" : "state-pill state-danger"}>{humanizeToken(service.status, locale)}</span>
                  </div>
                  <small>{summarizeServiceDetails(service, locale, t)}</small>
                </div>
                <div className="inline-actions">
                  <button className="text-button" onClick={() => onQuickRun("services.manage", {service_key: service.key, operation: "status"})}>{t("service.status")}</button>
                  <button className="text-button" onClick={() => onQuickRun("services.manage", {service_key: service.key, operation: "restart"})}>{t("service.restart")}</button>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="two-column-grid">
        <div className="surface-card">
          <SectionHeader kicker={t("overview.sshIdentity")} title={t("overview.managedUsers")} value={data.users.count} />
          <div className="row-list">
            {topUsers.map((user, index) => (
              <div className="info-row motion-rise" style={staggerStyle(index, 120, 45)} key={user.username}>
                <div>
                  <strong>{user.username}</strong>
                  <small>{t("overview.expiresOn", {value: user.expiry})}</small>
                </div>
                <div className="info-row-side">
                  <span>{t("overview.limit", {value: user.limit})}</span>
                  <span>{t("overview.online", {count: user.connected})}</span>
                  <button className="text-button" onClick={() => onQuickRun("users.disconnect", {username: user.username})}>{t("overview.disconnect")}</button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="surface-card">
          <SectionHeader kicker={t("overview.backupsAndDr")} title={t("overview.resilience")} value={data.backups.count} />
          <div className="row-list">
            {topJobs.length ? topJobs.map((job, index) => (
              <div className="info-row motion-rise" style={staggerStyle(index, 120, 45)} key={job.job_name}>
                <div>
                  <strong>{job.job_name}</strong>
                  <small>{humanizeToken(job.engine, locale)} / {humanizeToken(job.last_state, locale)}</small>
                </div>
                <button className="text-button" onClick={() => onQuickRun("dr.run_backup", {job_name: job.job_name})}>{t("overview.run")}</button>
              </div>
            )) : <div className="support-banner subdued">{t("overview.noBackupJobs")}</div>}
          </div>
          <div className="tag-cloud">
            {(data.open_ports || []).slice(0, 10).map((port) => (
              <span className="support-pill" key={`${port.protocol}-${port.host}-${port.port}`}>{port.protocol} {port.port || "-"}</span>
            ))}
          </div>
        </div>
      </section>

      <section className="surface-card">
        <SectionHeader kicker={t("overview.recentQueue")} title={t("overview.platformRuns")} value={tasks.length} />
        <div className="task-overview-grid">
          {topTasks.length ? topTasks.map((task, index) => (
            <button
              key={task.id}
              className={`task-tile task-${task.state || "queued"} motion-rise`}
              onClick={() => onOpenAction(task.action)}
              type="button"
              style={staggerStyle(index, 140, 55)}
            >
              <div className="row-title">
                <strong>{getTaskLabel(task.action, actionsById, locale)}</strong>
                <span>{humanizeToken(task.state, locale)}</span>
              </div>
              <p>{summarizeTaskResult(task, t)}</p>
              <small>{formatDate(task.startedAt, locale)}</small>
            </button>
          )) : <div className="support-banner subdued">{t("common.noTasks")}</div>}
        </div>
      </section>
    </div>
  );
}

function FleetPanel({overview, actionsById, onQuickRun, onOpenAction, t, locale}) {
  if (!overview) {
    return <div className="surface-card">{t("common.loadingInfra")}</div>;
  }

  const data = overview.overview;
  const shortcutActions = FLEET_SHORTCUT_ACTIONS.map((actionId) => actionsById[actionId]).filter(Boolean);

  return (
    <div className="page-grid">
      <section className="surface-card">
        <SectionHeader kicker={t("fleet.operationalFleet")} title={t("fleet.managedServices")} value={(data.managed_services || []).length} />
        <div className="service-card-grid">
          {(data.managed_services || []).map((service, index) => (
            <article className="service-tile motion-rise" style={staggerStyle(index, 80, 40)} key={service.key}>
              <div className="service-tile-head">
                <span className="chip-icon chip-icon-blue"><Icon name="dns" /></span>
                <div>
                  <strong>{service.name}</strong>
                  <small>{service.family}</small>
                </div>
              </div>
              <div className="service-meta">
                <span className={service.active ? "state-pill state-ok" : "state-pill state-danger"}>{humanizeToken(service.status, locale)}</span>
                <span className="support-pill">{Array.isArray(service.ports) ? (service.ports.join(", ") || t("service.noPorts")) : t("service.compositePorts")}</span>
              </div>
              <p className="body-copy tight service-description">{summarizeServiceDetails(service, locale, t)}</p>
              {getServiceContextActions(service, actionsById).length ? (
                <div className="tag-cloud">
                  {getServiceContextActions(service, actionsById).map((action) => (
                    <button
                      key={action.id}
                      type="button"
                      className="support-pill support-pill-button"
                      onClick={() => onOpenAction(action.id)}
                    >
                      {getActionLabel(action, locale)}
                    </button>
                  ))}
                </div>
              ) : null}
              <div className="inline-actions">
                <button className="text-button" onClick={() => onQuickRun("services.manage", {service_key: service.key, operation: "start"})}>{t("service.start")}</button>
                <button className="text-button" onClick={() => onQuickRun("services.manage", {service_key: service.key, operation: "stop"})}>{t("service.stop")}</button>
                <button className="text-button" onClick={() => onQuickRun("services.manage", {service_key: service.key, operation: "logs"})}>{t("service.logs")}</button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="surface-card">
        <SectionHeader kicker={t("common.dashboardCenter")} title={t("overview.actionCenters")} value={shortcutActions.length} />
        <div className="feature-action-grid">
          {shortcutActions.map((action, index) => {
            const meta = getCategoryMeta(action.category, locale);
            return (
              <button
                key={action.id}
                type="button"
                className="feature-action motion-rise"
                style={staggerStyle(index, 80, 36)}
                onClick={() => onOpenAction(action.id)}
              >
                <span className={`chip-icon chip-icon-${meta.tone}`}><Icon name={meta.icon} /></span>
                <div>
                  <strong>{getActionLabel(action, locale)}</strong>
                  <p>{getActionDescription(action)}</p>
                </div>
              </button>
            );
          })}
        </div>
      </section>

      <section className="two-column-grid">
        <div className="surface-card">
          <SectionHeader kicker={t("fleet.users")} title={t("fleet.sshAdjustments")} value={data.users?.count || 0} />
          <div className="row-list">
            {(data.users?.items || []).map((user, index) => (
              <div className="info-row motion-rise" style={staggerStyle(index, 100, 35)} key={user.username}>
                <div>
                  <strong>{user.username}</strong>
                  <small>{t("overview.limit", {value: user.limit})} / {t("overview.expiresOn", {value: user.expiry})}</small>
                </div>
                <div className="info-row-side">
                  <button className="text-button" onClick={() => onOpenAction("users.change_password", {username: user.username})}>{t("fleet.password")}</button>
                  <button className="text-button" onClick={() => onOpenAction("users.change_limit", {username: user.username})}>{t("fleet.limit")}</button>
                  <button className="text-button" onClick={() => onOpenAction("users.change_expiry", {username: user.username})}>{getActionLabel(actionsById["users.change_expiry"], locale)}</button>
                  <button className="text-button" onClick={() => onQuickRun("users.disconnect", {username: user.username})}>{t("overview.disconnect")}</button>
                  <button className="text-button danger-text-button" onClick={() => onOpenAction("users.delete", {username: user.username})}>{getActionLabel(actionsById["users.delete"], locale)}</button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="surface-card">
          <SectionHeader kicker={t("fleet.recovery")} title={t("fleet.drContext")} value={data.dr?.profiles_count || 0} />
          <div className="metric-stack">
            <div className="metric-inline">
              <span className="support-pill strong">{t("fleet.drProfiles")}</span>
              <strong>{data.dr.profiles_count}</strong>
            </div>
            <div className="metric-inline">
              <span className="support-pill strong">{t("fleet.drMonitors")}</span>
              <strong>{data.dr.monitors_count}</strong>
            </div>
            <div className="metric-inline">
              <span className="support-pill strong">{t("fleet.backupJobs")}</span>
              <strong>{data.backups.count}</strong>
            </div>
          </div>
          <div className="inline-actions inline-actions-wrap">
            {(data.backups?.items || []).slice(0, 2).map((job) => (
              <button key={job.job_name} className="text-button" onClick={() => onOpenAction("dr.backup_status", {job_name: job.job_name})}>{job.job_name}</button>
            ))}
            <button className="text-button" onClick={() => onOpenAction("dr.run_backup")}>{getActionLabel(actionsById["dr.run_backup"], locale)}</button>
            <button className="text-button" onClick={() => onOpenAction("dr.backup_status")}>{getActionLabel(actionsById["dr.backup_status"], locale)}</button>
            <button className="text-button" onClick={() => onOpenAction("dr.run_monitor")}>{getActionLabel(actionsById["dr.run_monitor"], locale)}</button>
            <button className="text-button" onClick={() => onOpenAction("dr.export_config")}>{t("fleet.exportConfigs")}</button>
            <button className="text-button" onClick={() => onOpenAction("dr.restore_test")}>{t("fleet.restoreTest")}</button>
          </div>
        </div>
      </section>
    </div>
  );
}

function OperationsPanel({actions, overview, actionsById, onRunAction, onOpenAction, runningAction, preset, searchSeed, t, locale}) {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [selectedActionId, setSelectedActionId] = useState(actions[0]?.id || "");
  const [workspace, setWorkspace] = useState("services");
  const [serviceSearch, setServiceSearch] = useState("");
  const [serviceFamily, setServiceFamily] = useState("all");
  const deferredSearch = useDeferredValue(search);
  const deferredServiceSearch = useDeferredValue(serviceSearch);

  useEffect(() => {
    if (!searchSeed?.nonce) {
      return;
    }
    setSearch(searchSeed.value || "");
  }, [searchSeed]);

  useEffect(() => {
    if (!actions.length) {
      setSelectedActionId("");
      return;
    }
    if (preset?.actionId) {
      setSelectedActionId(preset.actionId);
      setWorkspace(preset.actionId === "services.manage" ? "services" : "catalog");
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
  const selectedMeta = selectedAction ? getCategoryMeta(selectedAction.category, locale) : null;
  const managedServices = overview?.overview?.managed_services || [];
  const servicesLoading = !overview;
  const serviceFamilies = useMemo(() => {
    return Array.from(new Set(managedServices.map((service) => service.family).filter(Boolean)));
  }, [managedServices]);
  const filteredServices = useMemo(() => {
    return managedServices.filter((service) => {
      const matchesFamily = serviceFamily === "all" || service.family === serviceFamily;
      const haystack = `${service.name || ""} ${service.key || ""} ${service.family || ""} ${service.status || ""}`.toLowerCase();
      const matchesSearch = !deferredServiceSearch || haystack.includes(deferredServiceSearch.toLowerCase());
      return matchesFamily && matchesSearch;
    });
  }, [managedServices, serviceFamily, deferredServiceSearch]);

  return (
    <div className="page-grid">
      <section className="surface-card operations-tabs-shell">
        <div className="operations-tabs">
          <button
            type="button"
            className={workspace === "catalog" ? "operations-tab active" : "operations-tab"}
            onClick={() => setWorkspace("catalog")}
          >
            <span className="chip-icon chip-icon-blue"><Icon name="dashboard" /></span>
            <span className="operations-tab-copy">
              <strong>{t("operations.tabCatalog")}</strong>
              <small>{t("operations.tabCatalogDesc")}</small>
            </span>
          </button>
          <button
            type="button"
            className={workspace === "services" ? "operations-tab active" : "operations-tab"}
            onClick={() => setWorkspace("services")}
          >
            <span className="chip-icon chip-icon-teal"><Icon name="dns" /></span>
            <span className="operations-tab-copy">
              <strong>{t("operations.tabServices")}</strong>
              <small>{t("operations.tabServicesDesc")}</small>
            </span>
          </button>
        </div>
      </section>

      {workspace === "catalog" ? (
        <div className="page-grid">
          <section className="surface-card operations-browser operations-browser-wide">
            <div className="operations-browser-head">
              <SectionHeader kicker={t("operations.catalog")} title={t("operations.available")} value={actions.length} />
              <label className="search-inline">
                <Icon name="search" />
                <input
                  placeholder={t("common.searchActionCatalog")}
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </label>
              <div className="operations-filter-meta">
                <span className="support-pill strong">{t("operations.filtered", {count: filteredActions.length})}</span>
                {selectedMeta ? <span className="support-pill">{selectedMeta.label}</span> : null}
              </div>
              <div className="chip-row chip-row-scroll">
                <button className={category === "all" ? "filter-chip active" : "filter-chip"} onClick={() => setCategory("all")}>{t("common.all")}</button>
                {Object.keys(CATEGORY_META).map((key, index) => {
                  const meta = getCategoryMeta(key, locale);
                  return (
                    <button key={key} className={category === key ? "filter-chip active" : "filter-chip"} onClick={() => setCategory(key)} style={staggerStyle(index, 40, 35)}>{meta.label}</button>
                  );
                })}
              </div>
            </div>
            <div className="catalog-list catalog-list-grid">
              {filteredActions.map((action, index) => {
                const meta = getCategoryMeta(action.category, locale);
                return (
                  <button
                    key={action.id}
                    className={selectedAction?.id === action.id ? "catalog-item compact active motion-rise" : "catalog-item compact motion-rise"}
                    onClick={() => setSelectedActionId(action.id)}
                    style={staggerStyle(index, 120, 35)}
                  >
                    <span className={`chip-icon chip-icon-${meta.tone}`}>
                      <Icon name={meta.icon} />
                    </span>
                    <span className="catalog-copy">
                      <div className="catalog-title-row">
                        <strong>{getActionLabel(action, locale)}</strong>
                        <small>{meta.label}</small>
                      </div>
                      <p>{getActionDescription(action)}</p>
                    </span>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="surface-card operations-stage operations-stage-inline">
            {selectedAction ? (
              <ActionStage action={selectedAction} running={runningAction === selectedAction.id} onRunAction={onRunAction} preset={preset} t={t} locale={locale} />
            ) : (
              <div className="support-banner subdued">
                <strong>{t("operations.pickAction")}</strong>
                <span>{t("operations.pickActionCopy")}</span>
              </div>
            )}
          </section>
        </div>
      ) : (
        <section className="surface-card operations-services-panel">
          <div className="operations-browser-head operations-services-head">
            <SectionHeader kicker={t("operations.tabServices")} title={t("operations.serviceGridTitle")} value={filteredServices.length} />
            <p className="body-copy">{t("operations.serviceGridCopy")}</p>
            <label className="search-inline">
              <Icon name="search" />
              <input
                placeholder={t("operations.serviceSearch")}
                value={serviceSearch}
                onChange={(event) => setServiceSearch(event.target.value)}
              />
            </label>
            <div className="chip-row chip-row-scroll">
              <button className={serviceFamily === "all" ? "filter-chip active" : "filter-chip"} onClick={() => setServiceFamily("all")}>{t("operations.allFamilies")}</button>
              {serviceFamilies.map((family, index) => (
                <button
                  key={family}
                  className={serviceFamily === family ? "filter-chip active" : "filter-chip"}
                  onClick={() => setServiceFamily(family)}
                  style={staggerStyle(index, 40, 35)}
                >
                  {humanizeToken(family, locale)}
                </button>
              ))}
            </div>
          </div>
          {servicesLoading ? (
            <div className="support-banner subdued">{t("common.loadingInfra")}</div>
          ) : filteredServices.length ? (
            <div className="service-card-grid service-card-grid-operations">
              {filteredServices.map((service, index) => (
                <article className="service-tile motion-rise" style={staggerStyle(index, 80, 36)} key={service.key}>
                  <div className="service-tile-head">
                    <span className="chip-icon chip-icon-blue"><Icon name="dns" /></span>
                    <div>
                      <strong>{service.name}</strong>
                      <small>{humanizeToken(service.family, locale)}</small>
                    </div>
                  </div>
                  <div className="service-meta">
                    <span className={service.active ? "state-pill state-ok" : "state-pill state-danger"}>{humanizeToken(service.status, locale)}</span>
                    <span className="support-pill">{Array.isArray(service.ports) ? (service.ports.join(", ") || t("service.noPorts")) : t("service.compositePorts")}</span>
                  </div>
                  <p className="body-copy tight service-description">{summarizeServiceDetails(service, locale, t)}</p>
                  {getServiceContextActions(service, actionsById).length ? (
                    <div className="tag-cloud">
                      {getServiceContextActions(service, actionsById).map((action) => (
                        <button
                          key={action.id}
                          type="button"
                          className="support-pill support-pill-button"
                          onClick={() => onOpenAction(action.id)}
                        >
                          {getActionLabel(action, locale)}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  <div className="inline-actions inline-actions-wrap">
                    <button className="text-button" onClick={() => onRunAction("services.manage", {service_key: service.key, operation: "status"})}>{t("service.status")}</button>
                    <button className="text-button" onClick={() => onRunAction("services.manage", {service_key: service.key, operation: "start"})}>{t("service.start")}</button>
                    <button className="text-button" onClick={() => onRunAction("services.manage", {service_key: service.key, operation: "stop"})}>{t("service.stop")}</button>
                    <button className="text-button" onClick={() => onRunAction("services.manage", {service_key: service.key, operation: "restart"})}>{t("service.restart")}</button>
                    <button className="text-button" onClick={() => onRunAction("services.manage", {service_key: service.key, operation: "logs"})}>{t("service.logs")}</button>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="support-banner subdued">{t("operations.noServices")}</div>
          )}
        </section>
      )}
    </div>
  );
}

function ActionStage({action, onRunAction, running, preset, t, locale}) {
  const [form, setForm] = useState({});
  const meta = getCategoryMeta(action.category, locale);
  const {normalized, missing} = useMemo(() => validateActionForm(action, form), [action, form]);

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
    <div className="stack-lg">
      <div className="action-stage-head">
        <span className={`chip-icon chip-icon-${meta.tone}`}>
          <Icon name={meta.icon} />
        </span>
        <div>
          <div className="section-kicker">{meta.label}</div>
          <h3>{getActionLabel(action, locale)}</h3>
          <p className="body-copy">{getActionDescription(action)}</p>
        </div>
      </div>
      {action.dangerous ? <div className="support-banner warning">{t("common.sensitiveAction")}</div> : null}
      {missing.length ? <div className="support-banner subdued">{t("common.missingRequired")}</div> : null}
      <form className="stack-lg" onSubmit={(event) => {
        event.preventDefault();
        if (missing.length) {
          return;
        }
        onRunAction(action.id, normalized);
      }}>
        <div className="form-grid">
          {action.schema.map((field) => (
            <Field
              key={field.name}
              field={field}
              value={form[field.name]}
              t={t}
              onChange={(value) => setForm((current) => ({...current, [field.name]: value}))}
            />
          ))}
        </div>
        <button className="filled-button" type="submit" disabled={running || missing.length > 0}>
          {running ? t("common.submitting") : t("common.submitAction")}
        </button>
      </form>
    </div>
  );
}

function Field({field, value, onChange, t}) {
  if (field.type === "boolean") {
    return (
      <label className="toggle-field full-span">
        <div>
          <strong>{field.label}</strong>
          <small>{t("common.fieldToggleHint")}</small>
        </div>
        <input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />
      </label>
    );
  }

  if (field.type === "select") {
    return (
      <label className="input-field">
        <span>{field.label}{field.required ? ` · ${t("common.fieldRequired")}` : ""}</span>
        <select value={value} onChange={(event) => onChange(event.target.value)}>
          {(field.options || []).map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      </label>
    );
  }

  return (
    <label className={`input-field ${field.type === "textarea" ? "full-span" : ""}`}>
      <span>{field.label}{field.required ? ` · ${t("common.fieldRequired")}` : ""}</span>
      {field.type === "textarea" ? (
        <textarea value={value || ""} onChange={(event) => onChange(event.target.value)} rows={4} />
      ) : (
        <input
          type={field.type === "password" ? "password" : field.type === "number" ? "number" : "text"}
          value={value ?? ""}
          onChange={(event) => onChange(field.type === "number" ? (event.target.value === "" ? "" : Number(event.target.value)) : event.target.value)}
        />
      )}
    </label>
  );
}

function TasksPanel({tasks, selectedTask, onSelectTask, t, locale, actionsById}) {
  return (
    <div className="operations-layout">
      <section className="surface-card operations-browser">
        <SectionHeader kicker={t("tasks.queue")} title={t("tasks.recent")} value={tasks.length} />
        <div className="catalog-list">
          {tasks.length ? tasks.map((task, index) => (
            <button
              key={task.id}
              className={selectedTask?.id === task.id ? "catalog-item active motion-rise" : "catalog-item motion-rise"}
              onClick={() => onSelectTask(task.id)}
              style={staggerStyle(index, 100, 40)}
            >
              <span className={`chip-icon chip-icon-${taskTone(task.state)}`}>
                <Icon name="schedule" />
              </span>
              <span className="catalog-copy">
                <strong>{getTaskLabel(task.action, actionsById, locale)}</strong>
                <small>{humanizeToken(task.state, locale)}</small>
                <p>{summarizeTaskResult(task, t)}</p>
              </span>
            </button>
          )) : <div className="support-banner subdued">{t("common.noTasks")}</div>}
        </div>
      </section>

      <section className="surface-card operations-stage">
        {selectedTask ? (
          <div className="stack-lg">
            <SectionHeader kicker={t("tasks.execution")} title={getTaskLabel(selectedTask.action, actionsById, locale)} value={`${selectedTask.progress || 0}%`} />
            <div className="hero-stat-grid detail-stats">
              <HeroStat icon="schedule" tone={taskTone(selectedTask.state)} label={t("tasks.state")} value={humanizeToken(selectedTask.state, locale)} hint={t("tasks.currentStatus")} />
              <HeroStat icon="bolt" tone="blue" label={t("tasks.start")} value={formatDate(selectedTask.startedAt, locale)} hint={t("tasks.startHint")} />
              <HeroStat icon="info" tone="teal" label={t("tasks.end")} value={formatDate(selectedTask.finishedAt, locale)} hint={t("tasks.endHint")} />
            </div>
            <div className="progress-track"><div style={{width: `${selectedTask.progress || 0}%`}} /></div>
            <div className="support-banner result-summary">
              <strong>{t("common.resultSummary")}</strong>
              <span>{summarizeTaskResult(selectedTask, t) || t("common.noAdditionalDetails")}</span>
            </div>
          </div>
        ) : <div className="support-banner subdued">{t("common.selectTask")}</div>}
      </section>
    </div>
  );
}

function AboutPanel({overview, actions, t}) {
  return (
    <div className="page-grid">
      <section className="surface-card">
        <SectionHeader kicker={t("about.platform")} title={t("about.adminPanel")} />
        <p className="body-copy">
          {t("about.platformCopy")}
        </p>
      </section>

      <section className="two-column-grid">
        <div className="surface-card">
          <SectionHeader kicker={t("about.metadata")} title={t("about.technicalInfo")} />
          <div className="row-list">
            <div className="info-row"><strong>{t("about.scriptVersion")}</strong><span>{overview?.panel?.scriptVersion || "-"}</span></div>
            <div className="info-row"><strong>{t("about.panelVersion")}</strong><span>{overview?.panel?.panelVersion || "-"}</span></div>
            <div className="info-row"><strong>{t("about.python")}</strong><span>{overview?.panel?.pythonCommand || "-"}</span></div>
            <div className="info-row"><strong>{t("about.exposedActions")}</strong><span>{actions.length}</span></div>
          </div>
        </div>

        <div className="surface-card">
          <SectionHeader kicker={t("about.reading")} title={t("about.notes")} />
          <div className="tag-cloud">
            <span className="support-pill strong">{t("about.material3")}</span>
            <span className="support-pill">{t("about.largeIcons")}</span>
            <span className="support-pill">{t("about.cards")}</span>
            <span className="support-pill">{t("about.centralSearch")}</span>
            <span className="support-pill">{t("about.taskFlow")}</span>
          </div>
        </div>
      </section>
    </div>
  );
}

function taskTone(state) {
  if (state === "failed") {
    return "amber";
  }
  if (state === "completed") {
    return "green";
  }
  if (state === "running") {
    return "blue";
  }
  return "purple";
}

export default App;
