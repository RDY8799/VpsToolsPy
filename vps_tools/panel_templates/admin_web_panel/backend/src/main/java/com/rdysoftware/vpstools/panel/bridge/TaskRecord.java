package com.rdysoftware.vpstools.panel.bridge;

import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

public class TaskRecord {
    private final String id;
    private final String action;
    private final Map<String, Object> params;
    private final OffsetDateTime startedAt;
    private final List<Map<String, Object>> events = new CopyOnWriteArrayList<>();
    private final List<SseEmitter> emitters = new CopyOnWriteArrayList<>();
    private volatile String state = "queued";
    private volatile Integer progress = 0;
    private volatile String message = "Aguardando execucao";
    private volatile OffsetDateTime finishedAt;
    private volatile Object result;

    public TaskRecord(String id, String action, Map<String, Object> params) {
        this.id = id;
        this.action = action;
        this.params = params;
        this.startedAt = OffsetDateTime.now();
    }

    public String getId() {
        return id;
    }

    public void addEmitter(SseEmitter emitter) {
        emitters.add(emitter);
        emitter.onCompletion(() -> emitters.remove(emitter));
        emitter.onTimeout(() -> emitters.remove(emitter));
        replayTo(emitter);
    }

    public void addEvent(Map<String, Object> event) {
        events.add(event);
        if (event.containsKey("percent")) {
            Object value = event.get("percent");
            if (value instanceof Number number) {
                progress = number.intValue();
            }
        }
        if (event.containsKey("message")) {
            message = String.valueOf(event.get("message"));
        }
        if ("result".equals(event.get("type"))) {
            boolean ok = Boolean.TRUE.equals(event.get("ok"));
            state = ok ? "completed" : "failed";
            result = event.get("data");
            finishedAt = OffsetDateTime.now();
            progress = ok ? 100 : progress;
        } else if ("started".equals(event.get("type"))) {
            state = "running";
        } else if ("progress".equals(event.get("type"))) {
            state = "running";
        }
        broadcast(event);
    }

    public Map<String, Object> snapshot() {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("id", id);
        data.put("action", action);
        data.put("params", params);
        data.put("state", state);
        data.put("progress", progress);
        data.put("message", message);
        data.put("startedAt", startedAt);
        data.put("finishedAt", finishedAt);
        data.put("result", result);
        data.put("events", new ArrayList<>(events));
        return data;
    }

    private void replayTo(SseEmitter emitter) {
        for (Map<String, Object> event : events) {
            try {
                emitter.send(SseEmitter.event().name("task").data(event));
            } catch (IOException ignored) {
                emitters.remove(emitter);
                break;
            }
        }
    }

    private void broadcast(Map<String, Object> event) {
        for (SseEmitter emitter : emitters) {
            try {
                emitter.send(SseEmitter.event().name("task").data(event));
                if ("completed".equals(state) || "failed".equals(state)) {
                    emitter.complete();
                }
            } catch (IOException ignored) {
                emitters.remove(emitter);
            }
        }
    }
}
