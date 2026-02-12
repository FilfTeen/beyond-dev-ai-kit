package com.example.billing.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BillingController {
    @GetMapping("/billing/list")
    public String list() {
        return "ok";
    }
}
