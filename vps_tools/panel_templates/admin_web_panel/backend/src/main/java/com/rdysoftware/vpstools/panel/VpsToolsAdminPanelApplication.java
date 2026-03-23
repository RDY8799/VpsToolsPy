package com.rdysoftware.vpstools.panel;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class VpsToolsAdminPanelApplication {

    public static void main(String[] args) {
        SpringApplication.run(VpsToolsAdminPanelApplication.class, args);
    }
}
