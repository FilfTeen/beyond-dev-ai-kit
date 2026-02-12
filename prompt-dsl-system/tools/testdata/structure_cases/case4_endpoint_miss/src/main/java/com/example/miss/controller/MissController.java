package com.example.miss.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(ApiPrefix.ROOT)
public class MissController {
    @GetMapping(path = "/list")
    public Object list() {
        return null;
    }

    @PostMapping(path = "/save")
    public Object save() {
        return null;
    }
}

class ApiPrefix {
    static final String ROOT = "/miss";
}
