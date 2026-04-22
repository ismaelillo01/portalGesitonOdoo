/** @odoo-module **/

const PORTAL_CAROUSEL_SELECTOR = ".o_portal_internal_carousel";
const ITEM_SELECTOR = ".carousel-item";
const INDICATOR_SELECTOR = ".carousel-indicators button";
const PREV_SELECTOR = ".carousel-control-prev";
const NEXT_SELECTOR = ".carousel-control-next";
const INTERVAL_MS = 9000;

class PortalInternalCarousel {
    constructor(element) {
        this.element = element;
        this.items = [...element.querySelectorAll(ITEM_SELECTOR)];
        this.indicators = [...element.querySelectorAll(INDICATOR_SELECTOR)];
        this.prevButton = element.querySelector(PREV_SELECTOR);
        this.nextButton = element.querySelector(NEXT_SELECTOR);
        this.activeIndex = this._getInitialIndex();
        this.intervalId = null;
    }

    setup() {
        if (!this.items.length) {
            this._toggleControls(false);
            return;
        }
        this._syncDom();
        const canSlide = this.items.length > 1;
        this._toggleControls(canSlide);
        this._bindEvents(canSlide);
        if (canSlide) {
            this._startAutoPlay();
        }
    }

    _getInitialIndex() {
        const activeIndex = this.items.findIndex((item) => item.classList.contains("active"));
        return activeIndex >= 0 ? activeIndex : 0;
    }

    _syncDom() {
        this.items.forEach((item, index) => {
            item.classList.toggle("active", index === this.activeIndex);
        });
        this.indicators.forEach((indicator, index) => {
            const isActive = index === this.activeIndex;
            indicator.classList.toggle("active", isActive);
            if (isActive) {
                indicator.setAttribute("aria-current", "true");
            } else {
                indicator.removeAttribute("aria-current");
            }
        });
    }

    _toggleControls(visible) {
        for (const control of [this.prevButton, this.nextButton]) {
            if (!control) {
                continue;
            }
            control.classList.toggle("d-none", !visible);
            control.disabled = !visible;
        }
        const indicatorsContainer = this.element.querySelector(".carousel-indicators");
        if (indicatorsContainer) {
            indicatorsContainer.classList.toggle("d-none", !visible);
        }
    }

    _bindEvents(canSlide) {
        if (!canSlide) {
            return;
        }
        if (this.prevButton) {
            this.prevButton.addEventListener("click", (event) => {
                event.preventDefault();
                this.previous();
            });
        }
        if (this.nextButton) {
            this.nextButton.addEventListener("click", (event) => {
                event.preventDefault();
                this.next();
            });
        }
        this.indicators.forEach((indicator, index) => {
            indicator.addEventListener("click", (event) => {
                event.preventDefault();
                this.goTo(index);
            });
        });
        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "hidden") {
                this._stopAutoPlay();
            } else {
                this._startAutoPlay();
            }
        });
        this.element.addEventListener("mouseenter", () => this._stopAutoPlay());
        this.element.addEventListener("mouseleave", () => this._startAutoPlay());
    }

    goTo(index) {
        if (index < 0 || index >= this.items.length) {
            return;
        }
        this.activeIndex = index;
        this._syncDom();
        this._restartAutoPlay();
    }

    next() {
        this.goTo((this.activeIndex + 1) % this.items.length);
    }

    previous() {
        this.goTo((this.activeIndex - 1 + this.items.length) % this.items.length);
    }

    _startAutoPlay() {
        if (this.intervalId || this.items.length <= 1 || document.visibilityState === "hidden") {
            return;
        }
        this.intervalId = window.setInterval(() => this.next(), INTERVAL_MS);
    }

    _stopAutoPlay() {
        if (this.intervalId) {
            window.clearInterval(this.intervalId);
            this.intervalId = null;
        }
    }

    _restartAutoPlay() {
        this._stopAutoPlay();
        this._startAutoPlay();
    }
}

function initPortalInternalCarousels() {
    const carouselElements = document.querySelectorAll(PORTAL_CAROUSEL_SELECTOR);
    carouselElements.forEach((element) => {
        new PortalInternalCarousel(element).setup();
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPortalInternalCarousels, { once: true });
} else {
    initPortalInternalCarousels();
}
