package com.rdysoftware.vpstools.panel.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "vps.panel")
public class PanelProperties {
    private String username = "admin";
    private String password = "ChangeThisPassword123!";
    private String scriptRepoDir = "/root/VpsToolsPy";
    private String pythonCommand = "/root/VpsToolsPy/venv/bin/python";
    private String scriptVersion = "unknown";

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }

    public String getScriptRepoDir() {
        return scriptRepoDir;
    }

    public void setScriptRepoDir(String scriptRepoDir) {
        this.scriptRepoDir = scriptRepoDir;
    }

    public String getPythonCommand() {
        return pythonCommand;
    }

    public void setPythonCommand(String pythonCommand) {
        this.pythonCommand = pythonCommand;
    }

    public String getScriptVersion() {
        return scriptVersion;
    }

    public void setScriptVersion(String scriptVersion) {
        this.scriptVersion = scriptVersion;
    }
}
