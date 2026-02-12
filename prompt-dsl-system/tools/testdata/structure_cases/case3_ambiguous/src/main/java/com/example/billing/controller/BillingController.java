package com.example.billing.controller;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/billing")
public class BillingController {
    @GetMapping("/invoices")
    public Object invoices() {
        return null;
    }
}
