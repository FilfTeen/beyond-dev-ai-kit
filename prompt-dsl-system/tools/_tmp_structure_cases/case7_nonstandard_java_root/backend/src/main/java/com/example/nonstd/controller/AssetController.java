package com.example.nonstd.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AssetController {
    @GetMapping("/asset/list")
    public String list() {
        return "ok";
    }
}
