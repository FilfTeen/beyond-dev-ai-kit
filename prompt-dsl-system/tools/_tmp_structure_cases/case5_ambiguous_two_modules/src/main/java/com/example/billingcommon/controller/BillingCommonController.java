package com.example.billingcommon.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/billing-common")
public class BillingCommonController {
    @GetMapping("/summary")
    public Object summary() {
        return null;
    }
}
