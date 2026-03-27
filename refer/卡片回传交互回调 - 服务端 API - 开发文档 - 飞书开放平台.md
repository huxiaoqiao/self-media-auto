---
title: "卡片回传交互回调 - 服务端 API - 开发文档 - 飞书开放平台"
source: "https://open.feishu.cn/document/feishu-cards/card-callback-communication#65787609"
author:
published:
created: 2026-03-27
description: "卡片回传交互作用于飞书卡片的 请求回调 交互组件。当终端用户点击飞书卡片上的回传交互组件后，你在开发者后台应用内注册的回调请求地址将会收到 卡片回传交互 回调。该回调包含了用户与卡片之间的交互信息。"
tags:
  - "clippings"
---
## 卡片回传交互回调

最后更新于 2025-09-01

本文内容

**卡片回传交互** 作用于飞书卡片的 **请求回调** 交互组件。当终端用户点击飞书卡片上的回传交互组件后，你在开发者后台应用内注册的回调请求地址将会收到 **卡片回传交互** 回调。该回调包含了用户与卡片之间的交互信息。

你的业务服务器接收到回调请求后，需要在 3 秒内响应回调请求，声明通过弹出 Toast 提示、更新卡片、保持原内容不变等方式响应用户交互。了解详细的操作步骤，参考 [处理卡片回调](https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/handle-card-callbacks) 。

卡片回调和服务端响应回调的结构体参考下文。

## 回调

| 基本信息 |  |
| --- | --- |
| 回调类型 | card.action.trigger |
| 支持的应用类型 | 自建应用  商店应用 |
| 权限要求  开启任一权限即可 | 暂无 |
| 字段权限要求 | 获取用户 user ID  仅自建应用 |
| 推送方式 | [Webhook](https://open.feishu.cn/document/ukTMukTMukTM/uUTNz4SN1MjL1UzM) |

## 回调结构体

## 回调结构体示例

```
{
    "schema": "2.0", // 回调的版本
    "header": { // 回调基本信息
        "event_id": "f7984f25108f8137722bb63c*****", // 回调的唯一标识
        "token": "066zT6pS4QCbgj5Do145GfDbbag*****", // 应用的 Verification Token
        "create_time": "1603977298000000",  // 回调发送的时间，接近回调发生的时间。微秒级时间戳
        "event_type": "card.action.trigger", // 回调类型卡片交互场景中，固定为 "card.action.trigger"
        "tenant_key": "2df73991750*****", // 应用归属的 tenant key，即租户唯一标识
        "app_id": "cli_a5fb0ae6a4******" // 应用的 App ID
    },
    "event": { // 回调的详细信息
        "operator": {   // 回调触发者信息
            "tenant_key": "2df73991750*****", // 回调触发者的 tenant key，即租户唯一标识
            "user_id": "867*****", // 回调触发者的 user ID。当应用开启“获取用户 user ID”权限后，该参数返回
            "open_id": "ou_3c14f3a59eaf2825dbe25359f15*****", // 回调触发者的 Open ID
            "union_id": "on_cad4860e7af114fb4ff6c5d496d*****" // 回调触发者的 Union ID
        },
        "token": "c-295ee57216a5dc9de90fefd0aadb4b1d7d******", // 更新卡片用的凭证，有效期为 30 分钟，最多可更新 2 次
        "action": { // 用户操作交互组件回传的数据
            "value": { // 交互组件绑定的开发者自定义回传数据，对应组件中的 value 属性。类型为 string 或 object，可由开发者指定。
                "key": "value"
            },
            "tag": "button", // 交互组件的标签
            "timezone": "Asia/Shanghai", // 用户当前所在地区的时区。当用户操作日期选择器、时间选择器、或日期时间选择器时返回
            "form_value": { // 表单容器内用户提交的数据
                "field name1": [ // 表单容器内某多选组件的 name 和 value
                    "selectDemo1",
                    "selectDemo2"
                ],
                "field name2": "value2", // 表单容器内某交互组件的 name 和 value
                "DatePicker_bpqdq5puvn4": "2024-04-01 +0800", // 表单容器内日期选择器组件的 name 和 value
                "DateTimePicker_ihz2d7a74i": "2024-04-29 07:07 +0800", // 表单容器内日期时间选择器组件的 name 和 value
                "Input_lf4fmxwfrd9": "1234", // 表单容器内输入框组件的 name 和 value
                "PersonSelect_2ejys7ype7m": "ou_3c14f3a59eaf2825dbe25359f15*****", // 表单容器内人员选择-单选组件的 name 和 value
                "Select_a2d5b7l3zd": "1", // 表单容器内下拉选择-单选组件的 name 和 value
                "TimePicker_7ecsf6xkqsq": "00:00 +0800" // 表单容器内时间选择器组件的 name 和 value
            },
            "name": "Button_lvkepfu3" // 用户操作交互组件的名称，由开发者自定义
        },
        "host": "im_message", // 卡片展示场景
        "delivery_type": "url_preview", // 卡片分发类型，固定取值为 url_preview，表示链接预览卡片仅链接预览卡片有此字段
        "context": { //  卡片展示场景相关信息
            "url": "xxx", // 链接地址（适用于链接预览场景）
            "preview_token": "xxx", // 链接预览的 token（适用于链接预览场景）
            "open_message_id": "om_574d639e4a44e4dd646eaf628e2*****", // 卡片所在的消息 ID
            "open_chat_id": "oc_e4d2605ca917e695f54f11aaf56*****" // 卡片所在的会话 ID
        }
    }
}
```

## 响应回调的结构体

你的业务服务器接收到回调请求后，需要在 3 秒内响应回调请求，声明通过弹出 Toast 提示、更新卡片、保持原内容不变等方式响应用户交互。以下为使用卡片 JSON 代码和卡片模板响应的字段说明。要了解响应方式，参考 [处理卡片回调](https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/handle-card-callbacks) 。

业务服务端不可使用重定向状态码（ `HTTP 3xx` ）来响应卡片的回调请求，否则用户端将会出现交互请求错误。

### 使用卡片 JSON 代码响应

响应回调的结构体示例（以 JSON 2.0 结构为例）

```
{
    "toast": {
        "type": "info",
        "content": "卡片交互成功",
        "i18n": {
            "zh_cn": "卡片交互成功",
            "en_us": "card action success"
        }
    },
    "card": {
        "type": "raw",
        "data": {
            "schema": "2.0",
            "config": {
                "update_multi": true,
                "style": {
                    "text_size": {
                        "normal_v2": {
                            "default": "normal",
                            "pc": "normal",
                            "mobile": "heading"
                        }
                    }
                }
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "plain_text",
                            "content": "示例文本",
                            "text_size": "normal_v2",
                            "text_align": "left",
                            "text_color": "default"
                        },
                        "margin": "0px 0px 0px 0px"
                    }
                ]
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "示例标题"
                },
                "subtitle": {
                    "tag": "plain_text",
                    "content": "示例文本"
                },
                "template": "blue",
                "padding": "12px 12px 12px 12px"
            }
        }
    }
}
```

### 使用卡片模板响应

响应回调的结构体示例

```
{
    "toast": {
        "type": "info",
        "content": "卡片交互成功",
        "i18n": {
            "zh_cn": "卡片交互成功",
            "en_us": "card action success"
        }
    },
    "card": {
        "type": "template",
        "data": {
            "template_id": "AAqi6xJ8rabcd",
            "template_version_name": "1.0.0",
            "template_variable": {
                "open_id": "ou_d506829e8b6a17607e56bcd6b1aabcef"
            }
        }
    }
}
```

## 错误码

在飞书客户端进行卡片交互时，若交互出错，将返回如下图对应的错误码。错误码说明及解决方案如下表所示。

![](https://sf3-cn.feishucdn.com/obj/open-platform-opendoc/29558d328f22a099dc8ce5c66bf4e5ba_DD7lIR8Lxk.png?height=64&lazyload=true&width=285)

错误码仅支持飞书客户端 7.28 及以上版本。若未返回错误码，请升级飞书客户端后重试。

| 错误码 | 描述 | 解决方案 |
| --- | --- | --- |
| 200340 | 应用未配置飞书卡片回调地址或配置的请求地址无效。  若应用已配置，请确保你已创建并发布了最新的应用版本使修改生效。 | 1. 前往 [开发者后台](https://open.feishu.cn/app) ，点击目标应用，选择 **开发配置** > **事件与回调** 。 2. 在 **事件与回调** 页面 **回调配置** 页签下，填写正确有效的请求地址并保存。 	![回调配置](https://sf3-cn.feishucdn.com/obj/open-platform-opendoc/f014fb193c475cf0a335fcac883e3e82_fqr82G8RrO.png) 3. 在 **已订阅的回调** 项中，确保已添加卡片回传交互回调。 	![回调配置](https://sf3-cn.feishucdn.com/obj/open-platform-opendoc/1f1daabce2053bd9d94b828a6172aedd_QJM06G0lYC.png)  **提示** ：你也可以选择使用长连接接收回调。了解更多，参考 [配置回调订阅方式](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/event-subscription-guide/callback-subscription/configure-callback-request-address) 。 |
| 200341 | 所请求的卡片回调服务未在规定时间内响应飞书卡片服务端。 | 请确保配置的回调地址能够在 3 秒内响应卡片回调请求。 |
| 200342 | 飞书卡片服务端无法与该卡片回调地址建立 TCP 连接。 | 请检查并确保配置的回调地址可以正常访问。 |
| 200343 | 飞书卡片服务端解析该卡片回调地址的 DNS 失败。 | 请检查并确保配置的回调地址的域名正确。 |
| 200530 | 在表单容器中的交互组件的 name （表单项标识）属性为空。 | `name` 是表单容器内组件的唯一标识，用于识别用户提交的数据属于哪个组件，在单张卡片内不可为空、不可重复。  - 如果你使用卡片 JSON 搭建卡片，请确保所有的 name 属性的值不为空。 `name` 数据类型为字符串。 - 如果你使用卡片搭建工具搭建卡片： 	1. 在卡片编辑页面，选中表单内的交互组件，在右侧属性页签下，确保 **表单项标识** 已填写。 		![](https://sf3-cn.feishucdn.com/obj/open-platform-opendoc/93894aaf05f60f3576e64cb5a0f22569_62E0goGKeA.png?height=482&lazyload=true&width=1547) 		2. 点击右上角的 **保存** ，然后点击 **发布** ，确保修改生效。 		![](https://sf3-cn.feishucdn.com/obj/open-platform-opendoc/b704b7552c24d7956b402092c7c38775_c3K900pZqf.png?height=557&lazyload=true&width=1557) |
| 200080 | 飞书卡片服务端请求该卡片回调地址时发生错误。 | 请联系 [技术支持](https://applink.feishu.cn/TLJpeNdW) 进行处理。 |
| 200671 | 请求的卡片回调服务返回了非 `HTTP 200` 的状态码，导致无法进行正常的卡片交互。 | 请检查并确保接口代码逻辑正常，确保不会返回异常状态码。 |
| 200672 | 请求的卡片回调服务返回了错误的响应体格式。 | - 如果你添加的是新版卡片回传交互(`card.action.trigger`)回调，请参考 [卡片回传交互](https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/card-callback-communication#65787609) 检查响应回调的结构体的格式是否有误。 - 如果你添加的是旧版卡片回传交互(`card.action.trigger_v1`)回调，请参考 [消息卡片回传交互（旧）](https://open.feishu.cn/document/ukTMukTMukTM/uYzM3QjL2MzN04iNzcDN/configuring-card-callbacks/card-callback-structure) 检查响应回调的结构体的格式是否有误。 - 如果你同时添加了新版和旧版卡片回传交互回调，响应其中任一回调即为成功响应。建议你删除多余的请求方式。 |
| 200673 | 请求的卡片回调服务返回了错误的卡片。 | - 如果你添加的是新版卡片回传交互(`card.action.trigger`)回调，请参考 [卡片回传交互](https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/card-callback-communication#65787609) 检查响应回调的结构体中 `card` 部分是否有误。 - 如果你添加的是旧版卡片回传交互(`card.action.trigger_v1`)回调，请参考 [消息卡片回传交互（旧）](https://open.feishu.cn/document/ukTMukTMukTM/uYzM3QjL2MzN04iNzcDN/configuring-card-callbacks/card-callback-structure) 检查响应回调的结构体中除 `toast` 外的其它部分是否有误。 |
| 200830 | JSON 2.0 结构的卡片无法更新为 JSON 1.0 结构卡片。 | 如果交互前卡片的结构为 [卡片 JSON 2.0 结构](https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/card-json-v2-structure) ，交互后的卡片结构仍必须为 2.0 结构。 |
| 300000 | 服务内部错误。 | 请联系 [技术支持](https://applink.feishu.cn/TLJpeNdW) 。 |

本文内容

展开

拖拽到此处完成下载

图片将完成下载

AIX智能下载器