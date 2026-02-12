package com.example.order.controller;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping(value = "/api/order", produces = "application/json")
public class OrderController {
    @GetMapping(value = "/list", consumes = "application/json")
    public Object list() {
        return null;
    }

    @PostMapping("/create")
    public Object create() {
        return null;
    }

    @PutMapping("/update/{id}")
    public Object update(@PathVariable Long id) {
        return null;
    }
}
