import {browser} from "@web/core/browser/browser";
import {registry} from "@web/core/registry";

const TITLE_PREFIX_REGEX = /^\(\d+\)\s*/;

export function buildBadgedTitle(title, count) {
    const cleanTitle = (title || "").replace(TITLE_PREFIX_REGEX, "");
    return count > 0 ? `(${count}) ${cleanTitle}` : cleanTitle;
}

export function applyTitleBadge(title, count) {
    const nextTitle = buildBadgedTitle(title, count);
    document.title = nextTitle;
    return nextTitle;
}

export async function applyAppBadge(count, navigatorObject = navigator) {
    if (!navigatorObject) {
        return false;
    }
    if (count > 0 && navigatorObject.setAppBadge) {
        await navigatorObject.setAppBadge(count);
        return true;
    }
    if (count <= 0 && navigatorObject.clearAppBadge) {
        await navigatorObject.clearAppBadge();
        return true;
    }
    if (count === 0 && navigatorObject.setAppBadge) {
        await navigatorObject.setAppBadge(0);
        return true;
    }
    return false;
}

async function fetchBadgeCount() {
    const response = await browser.fetch("/pwa_badge/count", {
        method: "GET",
        credentials: "same-origin",
        headers: {
            Accept: "application/json",
        },
    });
    if (!response.ok) {
        throw new Error(`PWA badge request failed: ${response.status}`);
    }
    return response.json();
}

async function requestNotificationPermission(notificationObject = Notification) {
    if (!notificationObject || !notificationObject.requestPermission) {
        return "unsupported";
    }
    return notificationObject.requestPermission();
}

async function showSystemNotification(payload, state, notificationObject = Notification) {
    if (
        state.android_mode !== "system_notifications" ||
        !notificationObject ||
        notificationObject.permission !== "granted"
    ) {
        return;
    }
    const title = payload.title || "Nueva notificacion";
    const options = {
        body: payload.message || payload.body || "Tienes una nueva actualizacion.",
        tag: "pwa_badge_notification",
    };
    new notificationObject(title, options);
}

export const pwaBadgeService = {
    dependencies: ["bus_service"],

    start(env, {bus_service}) {
        const state = {
            titleFallback: true,
            android_mode: "best_effort",
            count_mode: "both",
            originalTitle: document.title,
            total_count: 0,
        };

        async function syncBadge() {
            try {
                const data = await fetchBadgeCount();
                state.android_mode = data.android_mode;
                state.count_mode = data.count_mode;
                state.titleFallback = data.title_fallback;
                state.total_count = data.total_count;

                const appBadgeApplied = await applyAppBadge(data.total_count);
                if (!appBadgeApplied && state.titleFallback) {
                    applyTitleBadge(state.originalTitle, data.total_count);
                } else {
                    applyTitleBadge(state.originalTitle, 0);
                }
            } catch {
                if (state.titleFallback) {
                    applyTitleBadge(state.originalTitle, state.total_count);
                }
            }
        }

        async function handlePermissionRequestClick(event) {
            const button = event.target.closest("[data-pwa-badge-request-permission]");
            if (!button) {
                return;
            }
            await requestNotificationPermission();
            await syncBadge();
        }

        async function handleBusRefresh(payload = {}) {
            await syncBadge();
            await showSystemNotification(payload, state);
        }

        document.addEventListener("click", handlePermissionRequestClick);
        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "visible") {
                syncBadge();
            }
        });
        window.addEventListener("focus", () => {
            syncBadge();
        });

        bus_service.subscribe("web_notify", (payload) => {
            handleBusRefresh(payload);
        });
        if (bus_service.addEventListener) {
            bus_service.addEventListener("notification", () => {
                syncBadge();
            });
        }
        bus_service.start();
        syncBadge();

        return {
            syncBadge,
            requestNotificationPermission,
        };
    },
};

registry.category("services").add("pwaBadge", pwaBadgeService);
