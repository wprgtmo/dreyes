/** @odoo-module **/

(() => {
    const path = window.location && window.location.pathname ? window.location.pathname : "";
    const isAuthPage = (
        path === "/web/login" ||
        path === "/web/login_successful" ||
        path === "/web/signup" ||
        path === "/web/reset_password"
    );
    if (isAuthPage) {
        document.documentElement.classList.add("sd_is_login");
        if (document.body) {
            document.body.classList.add("sd_is_login");
        }
    }
})();
