package com.example.composed.annotation;

import org.springframework.web.bind.annotation.GetMapping;

@GetMapping({"/items", API.Paths.EXTRA})
public @interface ComposedList {
}

class API {
    static class Paths {
        static final String EXTRA = "/extra";
    }
}
