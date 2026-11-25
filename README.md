# 应急附件卷的密钥代次迁移与退役

存储联调使用合成设备、时间轴和原始字节。设备记录由各客户端及介质的输入组成，每份记录可独立使用。

## 业务协议

密钥托管的本地交互只使用合成的不透明密钥句柄和字节串。 `POST /kms/{volume}/{epoch}/seal` 和 `POST /kms/{volume}/{epoch}/open` 接受二进制正文，回报 `file` 指有记录的密文或明文，`state=revoked` 表示服务拒绝再处理旧代次。内容相同的其他卷没有访问当前卷的能力。密钥服务记录用于验证调用方选择了针对哪个卷与代次的能力。
副本状态以卷、对象版本、设备和密文代次描述。`durable` 证明保存了字节，`verified` 还证明该卷可重新打开该字节且内容摘要匹配。资料给出已承诺的 `min_sites` 及储存预算。读凭据 `until` 到期不含端点，`hard_at` 是管理员判断不可延期吊销的业务时间。

## 本地设备资料

运行环境为 Python 3.11.2，使用标准库。设备资料端默认仅在 127.0.0.1:8090 运行，使用 --port 可另设端口。

~~~sh
python3 device_fixture.py fixtures/hard-retirement-before-replica-verification
~~~

GET /fixture/events 返回设备参数、字节目录和按到达顺序记录的输入。同一时刻按文件先后排列。GET /fixture/objects/文件名 取原始字节。GET /fixture/journal 查看资料端已收到的设备请求，每个请求记录实际正文长度和摘要。

events.json 中的 packets 是可重放的设备响应。资料端按实际 HTTP 方法、路径和完整原始请求正文匹配第一条尚未使用的记录。没有匹配时返回 404。lag_ms 是回包延迟，drop 代表设备收到请求后直接断开连接，接收方需要以其他报告确认结果。没有 HTTP 交互的设备和客户端动作直接取 events。重新启动资料端会回到记录开头。

在项目根目录运行 python3 -m unittest -v 检查事件、对应字节、设备响应及接收日志。
