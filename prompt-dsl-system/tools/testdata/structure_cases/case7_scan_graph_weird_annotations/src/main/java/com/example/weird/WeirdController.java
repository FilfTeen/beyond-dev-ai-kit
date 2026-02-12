package com.example.weird;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(ApiPaths.BASE)
public class WeirdController {

    private final WeirdService weirdService = new WeirdService();

    @GetMapping(ApiPaths.LIST)
    public String list() {
        return weirdService.ping();
    }
}
