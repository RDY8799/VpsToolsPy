package com.rdysoftware.vpstools.panel.bridge;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.rdysoftware.vpstools.panel.config.PanelProperties;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.stream.Collectors;

@Service
public class PanelBridgeService {
    private final PanelProperties properties;
    private final ObjectMapper objectMapper;
    private final Map<String, TaskRecord> tasks = new ConcurrentHashMap<>();
    private final ExecutorService executor = Executors.newCachedThreadPool();

    public PanelBridgeService(PanelProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    public Map<String, Object> loadOverview() {
        return runJsonCommand("overview");
    }

    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> loadActions() {
        Map<String, Object> wrapper = runJsonCommand("actions");
        Object actions = wrapper.get("actions");
        if (actions instanceof List<?> list) {
            return (List<Map<String, Object>>) list;
        }
        return List.of();
    }

    public Map<String, Object> panelMetadata() {
        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("panelName", "Painel Web Administrativo");
        meta.put("panelVersion", "0.1.0");
        meta.put("scriptVersion", properties.getScriptVersion());
        meta.put("repoDir", properties.getScriptRepoDir());
        meta.put("pythonCommand", properties.getPythonCommand());
        meta.put("timestamp", OffsetDateTime.now());
        return meta;
    }

    public TaskRecord startTask(String action, Map<String, Object> params) {
        String id = UUID.randomUUID().toString();
        TaskRecord record = new TaskRecord(id, action, params);
        tasks.put(id, record);
        executor.execute(() -> runTask(record));
        return record;
    }

    public List<Map<String, Object>> listTasks() {
        return tasks.values().stream()
                .map(TaskRecord::snapshot)
                .sorted((a, b) -> String.valueOf(b.get("startedAt")).compareTo(String.valueOf(a.get("startedAt"))))
                .collect(Collectors.toList());
    }

    public Map<String, Object> getTask(String id) {
        TaskRecord record = tasks.get(id);
        if (record == null) {
            return null;
        }
        return record.snapshot();
    }

    public SseEmitter streamTask(String id) {
        TaskRecord record = tasks.get(id);
        if (record == null) {
            throw new IllegalArgumentException("Task not found");
        }
        SseEmitter emitter = new SseEmitter(300_000L);
        record.addEmitter(emitter);
        return emitter;
    }

    private void runTask(TaskRecord record) {
        try {
            List<String> command = new ArrayList<>(baseCommand());
            command.add("run-action");
            command.add(record.snapshot().get("action").toString());
            command.add(objectMapper.writeValueAsString(record.snapshot().get("params")));

            ProcessBuilder processBuilder = new ProcessBuilder(command);
            processBuilder.directory(new File(properties.getScriptRepoDir()));
            processBuilder.redirectErrorStream(true);
            Process process = processBuilder.start();
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    if (line.isBlank()) {
                        continue;
                    }
                    Map<String, Object> event;
                    try {
                        event = objectMapper.readValue(line, new TypeReference<>() {
                        });
                    } catch (Exception parseError) {
                        event = new LinkedHashMap<>();
                        event.put("type", "log");
                        event.put("message", line);
                    }
                    record.addEvent(event);
                }
            }
            int exitCode = process.waitFor();
            if (exitCode != 0) {
                Map<String, Object> event = new LinkedHashMap<>();
                event.put("type", "result");
                event.put("ok", false);
                event.put("data", Map.of("message", "Processo do painel retornou código " + exitCode));
                record.addEvent(event);
            }
        } catch (Exception exc) {
            Map<String, Object> event = new LinkedHashMap<>();
            event.put("type", "result");
            event.put("ok", false);
            event.put("data", Map.of("message", exc.getMessage()));
            record.addEvent(event);
        }
    }

    private Map<String, Object> runJsonCommand(String command) {
        try {
            List<String> cmd = new ArrayList<>(baseCommand());
            cmd.add(command);
            ProcessBuilder processBuilder = new ProcessBuilder(cmd);
            processBuilder.directory(new File(properties.getScriptRepoDir()));
            processBuilder.redirectErrorStream(true);
            Process process = processBuilder.start();
            String output;
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                output = reader.lines().collect(Collectors.joining("\n"));
            }
            int exitCode = process.waitFor();
            if (exitCode != 0) {
                throw new IllegalStateException(output.isBlank() ? "Bridge command failed" : output);
            }
            JsonNode node = objectMapper.readTree(output);
            return objectMapper.convertValue(node, new TypeReference<>() {
            });
        } catch (IOException | InterruptedException exc) {
            throw new IllegalStateException(exc.getMessage(), exc);
        }
    }

    private List<String> baseCommand() {
        return List.of(
                properties.getPythonCommand(),
                "-m",
                "vps_tools.panel_bridge"
        );
    }
}
