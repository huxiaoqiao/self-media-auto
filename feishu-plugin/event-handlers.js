"use strict";
/**
 * Copyright (c) 2026 ByteDance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 *
 * Event handlers for the Feishu WebSocket monitor.
 *
 * Extracted from monitor.ts to improve testability and reduce
 * function size. Each handler receives a MonitorContext with all
 * dependencies needed to process the event.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.handleMessageEvent = handleMessageEvent;
exports.handleReactionEvent = handleReactionEvent;
exports.handleBotMembershipEvent = handleBotMembershipEvent;
exports.handleCardActionEvent = handleCardActionEvent;
const handler_1 = require("../messaging/inbound/handler");
const reaction_handler_1 = require("../messaging/inbound/reaction-handler");
const dedup_1 = require("../messaging/inbound/dedup");
const lark_ticket_1 = require("../core/lark-ticket");
const lark_logger_1 = require("../core/lark-logger");
const auto_auth_1 = require("../tools/auto-auth");
const chat_queue_1 = require("./chat-queue");
const abort_detect_1 = require("./abort-detect");
const elog = (0, lark_logger_1.larkLogger)('channel/event-handlers');
// ---------------------------------------------------------------------------
// Event ownership validation
// ---------------------------------------------------------------------------
/**
 * Verify that the event's app_id matches the current account.
 *
 * Lark SDK EventDispatcher flattens the v2 envelope header (which
 * contains `app_id`) into the handler `data` object, so `app_id` is
 * available directly on `data`.
 *
 * Returns `false` (discard event) when the app_id does not match.
 */
function isEventOwnershipValid(ctx, data) {
    const expectedAppId = ctx.lark.account.appId;
    if (!expectedAppId)
        return true; // appId not configured — skip check
    const eventAppId = data.app_id;
    if (eventAppId == null)
        return true; // SDK did not provide app_id — defensive skip
    if (eventAppId !== expectedAppId) {
        elog.warn('event app_id mismatch, discarding', {
            accountId: ctx.accountId,
            expected: expectedAppId,
            received: String(eventAppId),
        });
        return false;
    }
    return true;
}
// ---------------------------------------------------------------------------
// Message handler
// ---------------------------------------------------------------------------
async function handleMessageEvent(ctx, data) {
    if (!isEventOwnershipValid(ctx, data))
        return;
    const { accountId, log, error } = ctx;
    try {
        const event = data;
        const msgId = event.message?.message_id ?? 'unknown';
        const chatId = event.message?.chat_id ?? '';
        const threadId = event.message?.thread_id || undefined;
        // Dedup — skip duplicate messages (e.g. from WebSocket reconnects).
        if (!ctx.messageDedup.tryRecord(msgId, accountId)) {
            log(`feishu[${accountId}]: duplicate message ${msgId}, skipping`);
            return;
        }
        // Expiry — discard stale messages from reconnect replay.
        if ((0, dedup_1.isMessageExpired)(event.message?.create_time)) {
            log(`feishu[${accountId}]: message ${msgId} expired, discarding`);
            return;
        }
        // ---- Abort fast-path ----
        // If the message looks like an abort trigger and there is an active
        // reply dispatcher for this chat, fire abortCard() immediately
        // (before the message enters the serial queue) so the streaming
        // card is terminated without waiting for the current task.
        const abortText = (0, abort_detect_1.extractRawTextFromEvent)(event);
        if (abortText && (0, abort_detect_1.isLikelyAbortText)(abortText)) {
            const queueKey = (0, chat_queue_1.buildQueueKey)(accountId, chatId, threadId);
            if ((0, chat_queue_1.hasActiveTask)(queueKey)) {
                const active = (0, chat_queue_1.getActiveDispatcher)(queueKey);
                if (active) {
                    log(`feishu[${accountId}]: abort fast-path triggered for chat ${chatId} (text="${abortText}")`);
                    active.abortController?.abort();
                    active.abortCard().catch((err) => {
                        error(`feishu[${accountId}]: abort fast-path abortCard failed: ${String(err)}`);
                    });
                }
            }
        }
        const { status } = (0, chat_queue_1.enqueueFeishuChatTask)({
            accountId,
            chatId,
            threadId,
            task: async () => {
                try {
                    await (0, lark_ticket_1.withTicket)({
                        messageId: msgId,
                        chatId,
                        accountId,
                        startTime: Date.now(),
                        senderOpenId: event.sender?.sender_id?.open_id || '',
                        chatType: event.message?.chat_type || undefined,
                        threadId,
                    }, () => (0, handler_1.handleFeishuMessage)({
                        cfg: ctx.cfg,
                        event,
                        botOpenId: ctx.lark.botOpenId,
                        runtime: ctx.runtime,
                        chatHistories: ctx.chatHistories,
                        accountId,
                    }));
                }
                catch (err) {
                    error(`feishu[${accountId}]: error handling message: ${String(err)}`);
                }
            },
        });
        log(`feishu[${accountId}]: message ${msgId} in chat ${chatId}${threadId ? ` thread ${threadId}` : ''} — ${status}`);
    }
    catch (err) {
        error(`feishu[${accountId}]: error handling message: ${String(err)}`);
    }
}
// ---------------------------------------------------------------------------
// Reaction handler
// ---------------------------------------------------------------------------
async function handleReactionEvent(ctx, data) {
    if (!isEventOwnershipValid(ctx, data))
        return;
    const { accountId, log, error } = ctx;
    try {
        const event = data;
        const msgId = event.message_id ?? 'unknown';
        log(`feishu[${accountId}]: reaction event on message ${msgId}`);
        // ---- Dedup: deterministic key based on message + emoji + operator ----
        const emojiType = event.reaction_type?.emoji_type ?? '';
        const operatorOpenId = event.user_id?.open_id ?? '';
        const dedupKey = `${msgId}:reaction:${emojiType}:${operatorOpenId}`;
        if (!ctx.messageDedup.tryRecord(dedupKey, accountId)) {
            log(`feishu[${accountId}]: duplicate reaction ${dedupKey}, skipping`);
            return;
        }
        // ---- Expiry: discard stale reaction events ----
        if ((0, dedup_1.isMessageExpired)(event.action_time)) {
            log(`feishu[${accountId}]: reaction on ${msgId} expired, discarding`);
            return;
        }
        // ---- Pre-resolve real chatId before enqueuing ----
        // The API call (3s timeout) runs outside the queue so it doesn't
        // block the serial chain, and is read-only so ordering is irrelevant.
        const preResolved = await (0, reaction_handler_1.resolveReactionContext)({
            cfg: ctx.cfg,
            event,
            botOpenId: ctx.lark.botOpenId,
            runtime: ctx.runtime,
            accountId,
        });
        if (!preResolved)
            return;
        // ---- Enqueue with the real chatId (matches normal message queue key) ----
        const { status } = (0, chat_queue_1.enqueueFeishuChatTask)({
            accountId,
            chatId: preResolved.chatId,
            threadId: preResolved.threadId,
            task: async () => {
                try {
                    await (0, lark_ticket_1.withTicket)({
                        messageId: msgId,
                        chatId: preResolved.chatId,
                        accountId,
                        startTime: Date.now(),
                        senderOpenId: operatorOpenId,
                        chatType: preResolved.chatType,
                        threadId: preResolved.threadId,
                    }, () => (0, reaction_handler_1.handleFeishuReaction)({
                        cfg: ctx.cfg,
                        event,
                        botOpenId: ctx.lark.botOpenId,
                        runtime: ctx.runtime,
                        chatHistories: ctx.chatHistories,
                        accountId,
                        preResolved,
                    }));
                }
                catch (err) {
                    error(`feishu[${accountId}]: error handling reaction: ${String(err)}`);
                }
            },
        });
        log(`feishu[${accountId}]: reaction on ${msgId} (chatId=${preResolved.chatId}) — ${status}`);
    }
    catch (err) {
        error(`feishu[${accountId}]: error handling reaction event: ${String(err)}`);
    }
}
// ---------------------------------------------------------------------------
// Bot membership handler
// ---------------------------------------------------------------------------
async function handleBotMembershipEvent(ctx, data, action) {
    if (!isEventOwnershipValid(ctx, data))
        return;
    const { accountId, log, error } = ctx;
    try {
        const event = data;
        log(`feishu[${accountId}]: bot ${action} ${action === 'removed' ? 'from' : 'to'} chat ${event.chat_id}`);
    }
    catch (err) {
        error(`feishu[${accountId}]: error handling bot ${action} event: ${String(err)}`);
    }
}
// ---------------------------------------------------------------------------
// Card action handler
// ---------------------------------------------------------------------------
async function handleCardActionEvent(ctx, data) {
    try {
        // 首先尝试自动授权逻辑（OAuth类动作）
        const autoAuthResult = await (0, auto_auth_1.handleCardAction)(data, ctx.cfg, ctx.accountId);
        // 如果 handleCardAction 返回了响应（说明是 OAuth 相关动作），直接返回
        if (autoAuthResult) {
            return autoAuthResult;
        }
    }
    catch (err) {
        elog.warn(`card.action.trigger auto-auth error: ${err}`);
    }

    // ---- 自定义按钮动作处理（转发为文本命令）----
    // 当 handleCardAction 返回 undefined 时，说明不是 OAuth 动作，而是我们的自定义按钮
    try {
        const event = data;
        // 兼容多种嵌套结构: data.action.value 或 data.event.action.value
        const rawActionValue = event.action?.value ?? event.event?.action?.value;
        if (!rawActionValue) {
            elog.warn('feishu[' + ctx.accountId + ']: card action but no action value found, event keys: ' + Object.keys(event));
            return;
        }
        const actionValue = typeof rawActionValue === 'string' ? rawActionValue : JSON.stringify(rawActionValue);
        elog.info('feishu[' + ctx.accountId + ']: card button clicked, actionValue type: ' + typeof rawActionValue + ', value: ' + actionValue);

        // actionValue 是字符串，如 'rewrite_script_01'
        const actionValueStr = typeof actionValue === 'string' ? actionValue : '';
        const action = actionValueStr.split('_')[0];  // 'rewrite'
        const reviewId = actionValueStr.split('_')[1] || '';  // 'script_01'
        const cardServerActions = ['rewrite', 'approve', 'modify', 'rescript', 'rearticle', 'post', 'copy', 'cancel', 'insight', 'next', 'init'];
        if (action && cardServerActions.some(a => action.startsWith(a))) {
            // 修复: 将 Feishu 嵌套结构转换为扁平结构，供 OpenClaw 核心代码解析
            // Feishu 原始结构: { header: {...}, event: { action, operator, context } }
            // OpenClaw 期望结构: { action, operator, context, token } (扁平)
            if (data.event && !data.action) {
                const feishuEvent = data.event;
                data.action = feishuEvent.action;
                data.operator = feishuEvent.operator;
                data.context = feishuEvent.context;
                data.token = data.header?.token || '';
                // 删除嵌套结构，防止重复处理
                delete data.event;
                delete data.header;
                elog.info('feishu[' + ctx.accountId + ']: transformed nested event to flat structure');
            }
            // 转发回调请求到卡服务器
            const cardServerUrl = 'http://localhost:18799/feishu/callback';
            const eventData = JSON.stringify(data);
            try {
                const response = await fetch(cardServerUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: eventData
                });
                elog.info('feishu[' + ctx.accountId + ']: card action ' + action + ' forwarded to card server, status: ' + response.status);
            } catch (err) {
                elog.warn('feishu[' + ctx.accountId + ']: forward to card server failed: ' + err);
            }
            return;  // 不再处理，让卡服务器处理
        }

        // 构造文本命令（仅处理选题卡片的 insight/refresh 动作）
        let textCommand = null;
        if (action === 'insight' && topicId) {
            textCommand = String(topicId);
        } else if (action === 'refresh') {
            textCommand = '换一批';
        }

        if (!textCommand) return;
        const chatId = event.message?.chat_id || '';
        const threadId = event.message?.thread_id || undefined;
        const msgId = event.message?.message_id || `card_${Date.now()}`;
        const senderOpenId = event.operator?.open_id || '';

        if (!chatId) return;

        // 注入为文本消息，触发 agent 正常处理流程
        const syntheticEvent = {
            sender: { sender_id: { open_id: senderOpenId } },
            message: {
                message_id: `card_cmd_${Date.now()}`,
                chat_id: chatId,
                chat_type: event.message?.chat_type || 'p2p',
                message_type: 'text',
                content: JSON.stringify({ text: textCommand }),
                thread_id: threadId,
                create_time: Math.floor(Date.now() / 1000).toString(),
            },
        };

        const { status } = (0, chat_queue_1.enqueueFeishuChatTask)({
            accountId: ctx.accountId,
            chatId,
            threadId,
            task: async () => {
                try {
                    await (0, lark_ticket_1.withTicket)({
                        messageId: msgId,
                        chatId,
                        accountId: ctx.accountId,
                        startTime: Date.now(),
                        senderOpenId,
                        chatType: event.message?.chat_type || undefined,
                        threadId,
                    }, () => (0, handler_1.handleFeishuMessage)({
                        cfg: ctx.cfg,
                        event: syntheticEvent,
                        botOpenId: ctx.lark.botOpenId,
                        runtime: ctx.runtime,
                        chatHistories: ctx.chatHistories,
                        accountId: ctx.accountId,
                    }));
                }
                catch (err) {
                    ctx.error(`feishu[${ctx.accountId}]: error handling card command: ${String(err)}`);
                }
            },
        });

        elog.info(`feishu[${ctx.accountId}]: card action "${action}" topic_id=${topicId} enqueued as "${textCommand}" - ${status}`);
    }
    catch (err) {
        elog.warn(`card.action.trigger custom handling error: ${err}`);
    }
}
