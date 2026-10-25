/** @odoo-module **/

import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { formatFloat } from "@web/core/utils/numbers";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class PricingTable extends Component {
    static template = "dreyes_product_pricing.PricingTable";
    static props = { sourceModel: String, sourceId: { type: [Number, Boolean], optional: true } };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.requestNumber = 0;
        this.state = useState({
            rows: [], total: 0, offset: 0, limit: 80,
            quantity: "1", date: "", search: "",
            appliedQuantity: 1, appliedDate: "",
            loading: false, saving: false, error: "", drafts: {},
        });
        onWillStart(() => this.load());
        onWillUpdateProps(async (nextProps) => {
            if (nextProps.sourceId !== this.props.sourceId || nextProps.sourceModel !== this.props.sourceModel) {
                this.state.offset = 0;
                this.state.search = "";
                this.state.drafts = {};
                await this.load(nextProps);
            }
        });
    }

    get hasEditableRows() {
        return this.state.rows.some((row) => row.can_edit);
    }

    get rangeLabel() {
        if (!this.state.total) {
            return "0 / 0";
        }
        return `${this.state.offset + 1}–${this.state.offset + this.state.rows.length} / ${this.state.total}`;
    }

    formatPrice(row) {
        return formatFloat(row.price, { digits: [16, row.currency_digits] });
    }

    errorMessage(error) {
        return error.data?.message || error.message || _t("No se pudo completar la operación.");
    }

    async load(props = this.props) {
        const requestNumber = ++this.requestNumber;
        this.state.error = "";
        if (!props.sourceId) {
            this.state.rows = [];
            this.state.total = 0;
            this.state.loading = false;
            return;
        }
        const quantity = Number(this.state.quantity);
        if (!Number.isFinite(quantity) || quantity <= 0) {
            this.state.error = _t("La cantidad debe ser un número mayor que cero.");
            this.state.loading = false;
            return;
        }
        this.state.loading = true;
        try {
            const result = await this.orm.call("product.pricelist", "dreyes_get_price_page", [], {
                source_model: props.sourceModel, source_id: props.sourceId,
                quantity, date: this.state.date || false,
                search: this.state.search, offset: this.state.offset, limit: this.state.limit,
            });
            if (requestNumber !== this.requestNumber) {
                return;
            }
            Object.assign(this.state, {
                rows: result.rows, total: result.total, offset: result.offset,
                date: result.date, drafts: {},
                appliedQuantity: result.quantity, appliedDate: result.date,
            });
        } catch (error) {
            if (requestNumber === this.requestNumber) {
                this.state.rows = [];
                this.state.total = 0;
                this.state.error = this.errorMessage(error);
            }
        } finally {
            if (requestNumber === this.requestNumber) {
                this.state.loading = false;
            }
        }
    }

    async refresh() {
        this.state.offset = 0;
        await this.load();
    }

    async changePage(direction) {
        this.state.offset = Math.max(0, this.state.offset + direction * this.state.limit);
        await this.load();
    }

    async openRecord(model, id) {
        await this.action.doAction({
            type: "ir.actions.act_window", res_model: model, res_id: id,
            views: [[false, "form"]], target: "current",
        });
    }

    updateDraft(row, event) {
        this.state.drafts[row.key] = event.target.value;
    }

    async save(row) {
        const draft = this.state.drafts[row.key];
        const price = Number(draft);
        if (draft === undefined || draft.trim() === "" || !Number.isFinite(price) || price < 0) {
            this.notification.add(_t("Introduzca un precio fijo mayor o igual que cero."), { type: "warning" });
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call("product.pricelist", "dreyes_save_fixed_price", [], {
                pricelist_id: row.pricelist_id, product_id: row.product_id, price,
                quantity: this.state.appliedQuantity, date: this.state.appliedDate,
            });
            if (result.status === "duplicates") {
                this.notification.add(_t("Hay varias excepciones iguales. Revise las reglas antes de guardar."), {
                    type: "warning",
                });
                await this.action.doAction(result.action, { onClose: () => this.load() });
                return;
            }
            const index = this.state.rows.findIndex((existing) => existing.key === row.key);
            if (index !== -1) {
                this.state.rows[index] = result.row;
            }
            delete this.state.drafts[row.key];
            this.notification.add(
                result.overridden
                    ? _t("Precio fijo guardado. Otra regla determina el precio para la cantidad y fecha consultadas.")
                    : _t("Precio fijo guardado."),
                { type: result.overridden ? "warning" : "success" }
            );
        } catch (error) {
            this.notification.add(this.errorMessage(error), { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }
}

class ProductPricingWidget extends Component {
    static template = "dreyes_product_pricing.ProductPricingWidget";
    static components = { PricingTable };
    static props = { ...standardWidgetProps };
}

class PricingCatalogAction extends Component {
    static template = "dreyes_product_pricing.PricingCatalogAction";
    static components = { PricingTable, Layout };
    static props = { ...standardActionServiceProps };
    static displayName = _t("Productos y precios");

    setup() {
        this.sourceId = this.props.action.params?.source_id || this.props.resId || false;
        // Native action state preserves this record ID in the URL across reloads.
        if (this.sourceId) {
            this.props.updateActionState({ resId: this.sourceId });
        }
    }
}

registry.category("view_widgets").add("dreyes_product_pricing_table", { component: ProductPricingWidget });
registry.category("actions").add("dreyes_product_pricing.catalog", PricingCatalogAction);
