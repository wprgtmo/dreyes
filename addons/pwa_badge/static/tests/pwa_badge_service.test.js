import {expect, test} from "@odoo/hoot";

import {
    applyAppBadge,
    applyTitleBadge,
    buildBadgedTitle,
} from "../src/js/pwa_badge_service.esm";

test("buildBadgedTitle prefixes the title with the counter", () => {
    expect(buildBadgedTitle("Inbox", 4)).toBe("(4) Inbox");
});

test("buildBadgedTitle removes an existing prefix before applying a new one", () => {
    expect(buildBadgedTitle("(9) Inbox", 2)).toBe("(2) Inbox");
});

test("applyTitleBadge clears the prefix when count is zero", () => {
    document.title = "(7) Inbox";
    applyTitleBadge(document.title, 0);
    expect(document.title).toBe("Inbox");
});

test("applyAppBadge uses setAppBadge when count is positive", async () => {
    const calls = [];
    const navigatorObject = {
        async setAppBadge(value) {
            calls.push(["set", value]);
        },
    };
    const result = await applyAppBadge(5, navigatorObject);
    expect(result).toBe(true);
    expect(calls).toEqual([["set", 5]]);
});

test("applyAppBadge uses clearAppBadge when count is zero", async () => {
    const calls = [];
    const navigatorObject = {
        async clearAppBadge() {
            calls.push(["clear"]);
        },
    };
    const result = await applyAppBadge(0, navigatorObject);
    expect(result).toBe(true);
    expect(calls).toEqual([["clear"]]);
});
