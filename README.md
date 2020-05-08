### 原理介绍

concurrent http client 是基于 I/O 多路复用机制、 libcurl multi 接口以及多线程实现的并发 HTTP 客户端。

其主要原理是：客户端向 concurrent http client 提交请求时， concurrent http client 会将请求放到内部的队列中，并立即返回给客户端一个 Future 对象，因此不会阻塞客户端，客户端可以通过在 Future 对象上等待或注册回调函数的方式，获取响应。 concurrent http client 在启动时，会创建若干个线程（由 `worker_count` 参数指定），每个线程内部会创建一个事件循环（ EventLoop 对象）和一个 curl multi 对象。其中，事件循环负责在 curl multi 所关注的文件描述符上发生事件或超时时，通知 curl multi ，并从 curl multi 中“拉取”已完成的请求，然后将响应“填充”到相应的 Future 对象中； curl multi 负责并发地传输多个请求。

EventLoop 对象根据下面的优先级选择使用的 I/O 多路复用机制：

* 如果操作系统支持 epoll ，则使用 epoll
* 如果操作系统支持 kqueue ，则使用 kqueue
* 否则，使用 select

curl multi （文档地址：[https://curl.haxx.se/libcurl/c/libcurl-multi.html](https://curl.haxx.se/libcurl/c/libcurl-multi.html)）提供多个 curl 不支持的功能，主要包括：

* 支持“拉取”（ `pull` ）接口，由应用程序决定何时让 libcurl 获取或发送数据

* 支持在单个线程中，同时传输多个请求

* 支持应用程序同时地在它自己的文件描述符和 curl 的文件描述符上等待事件

* 支持**基于事件**的处理，提高到在数以千计的并发连接上传输数据

concurrent http client 支持下面的特性：

* 通过 curl ，支持获取处理请求的各个阶段所消耗的时间，包括：[总耗时](https://curl.haxx.se/libcurl/c/CURLINFO_TOTAL_TIME.html)、[域名解析耗时](https://curl.haxx.se/libcurl/c/CURLINFO_NAMELOOKUP_TIME.html)、[连接耗时](https://curl.haxx.se/libcurl/c/CURLINFO_CONNECT_TIME.html)、[SSL/SSH握手耗时](https://curl.haxx.se/libcurl/c/CURLINFO_APPCONNECT_TIME.html)、[从发起请求到传输开始的耗时](https://curl.haxx.se/libcurl/c/CURLINFO_PRETRANSFER_TIME.html)、[从发起请求到收到第一个字节的耗时](https://curl.haxx.se/libcurl/c/CURLINFO_STARTTRANSFER_TIME.html)、[重定向耗时](https://curl.haxx.se/libcurl/c/CURLINFO_REDIRECT_TIME.html)等，以及上传速度、下载速度等

* 通过 curl 的 [RESOLVE](https://curl.haxx.se/libcurl/c/CURLOPT_RESOLVE.html) 选项，支持将域名解析到固定的 IP 列表上（可以替代 /etc/hosts ）

* 通过 curl 的 [CONNECT\_TO](https://curl.haxx.se/libcurl/c/CURLOPT_CONNECT_TO.html) 选项，支持连接到特定的 HOST 和 PORT 上，而不是连接到 URL 中的 HOST 和 PORT 上（类似 DNS 的 CNAME）

* 通过 curl 的 [DNS\_SERVERS](https://curl.haxx.se/libcurl/c/CURLOPT_DNS_SERVERS.html) 选项，支持自定义 DNS 服务器列表

* **限制响应体的大小**，以避免浪费资源。比如，当抓取一个链接时，如果被对方服务器识别为恶意抓取程序，那么它可能将请求重定向到一个“黑洞”中，该“黑洞”会源源不断地向客户端传送数据，直到客户端崩溃（比如，内存耗尽或磁盘耗尽），在这样的场景中就应该考虑对响应体的大小进行限制

* 等

---

### 环境要求

* curl 7.42及以上版本

