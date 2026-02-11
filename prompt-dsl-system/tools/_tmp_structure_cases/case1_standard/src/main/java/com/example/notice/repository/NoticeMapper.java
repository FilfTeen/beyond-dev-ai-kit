package com.example.notice.repository;

import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface NoticeMapper {
    Object selectList();

    int insert(Object entity);
}
