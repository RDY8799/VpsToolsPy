package com.rdysoftware.vpstools.panel.web;

import com.rdysoftware.vpstools.panel.bridge.PanelBridgeService;
import com.rdysoftware.vpstools.panel.bridge.TaskRecord;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api")
public class PanelController {
    private final PanelBridgeService bridgeService;

    public PanelController(PanelBridgeService bridgeService) {
        this.bridgeService = bridgeService;
    }

    @GetMapping("/overview")
    public Map<String, Object> overview() {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("overview", bridgeService.loadOverview());
        data.put("panel", bridgeService.panelMetadata());
        return data;
    }

    @GetMapping("/actions")
    public Map<String, Object> actions() {
        return Map.of("actions", bridgeService.loadActions());
    }

    @GetMapping("/tasks")
    public Map<String, Object> tasks() {
        return Map.of("tasks", bridgeService.listTasks());
    }

    @GetMapping("/tasks/{id}")
    public ResponseEntity<?> task(@PathVariable String id) {
        Map<String, Object> task = bridgeService.getTask(id);
        if (task == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("message", "Tarefa nao encontrada"));
        }
        return ResponseEntity.ok(task);
    }

    @GetMapping("/tasks/{id}/stream")
    public SseEmitter stream(@PathVariable String id) {
        return bridgeService.streamTask(id);
    }

    @PostMapping("/tasks")
    public ResponseEntity<?> createTask(@Valid @RequestBody CreateTaskRequest request) {
        TaskRecord record = bridgeService.startTask(request.action(), request.params() == null ? Map.of() : request.params());
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(record.snapshot());
    }

    public record CreateTaskRequest(@NotBlank String action, Map<String, Object> params) {
    }
}
