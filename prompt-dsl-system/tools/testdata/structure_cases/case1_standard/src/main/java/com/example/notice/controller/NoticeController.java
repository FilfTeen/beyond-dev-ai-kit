package com.example.notice.controller;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/notice")
public class NoticeController {
    @GetMapping("/list")
    public Object list() { return null; }
    @PostMapping("/save")
    public Object save() { return null; }
    @DeleteMapping("/delete/{id}")
    public Object delete(@PathVariable Long id) { return null; }
}
