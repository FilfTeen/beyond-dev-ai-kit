package com.example.composed.controller;

import com.example.composed.annotation.ComposedList;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(ApiPrefix.ROOT)
public class ComposedController {
    @ComposedList
    public Object list() {
        return null;
    }
}

class ApiPrefix {
    static final String ROOT = "/composed";
}
