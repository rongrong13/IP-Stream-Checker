# -*- coding: utf-8 -*-
"""流媒体解锁检测集成模块

调用 MediaUnlockTest(Go 编写的流媒体解锁检测工具)对指定代理执行解锁测试,
解析其 -json 模式输出的结构化结果,并生成用于节点名标注的短摘要。

依赖:
    mediatest 二进制(由 Dockerfile 多阶段构建生成)
"""
