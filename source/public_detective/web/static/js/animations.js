// Register GSAP plugins
gsap.registerPlugin(ScrollTrigger);

// Page Transition Animation
document.addEventListener('htmx:afterSwap', (event) => {
    // Re-initialize animations after content swap
    initAnimations();
});

document.addEventListener('DOMContentLoaded', () => {
    initAnimations();
});

function initAnimations() {
    // Fade in main content
    gsap.from("#main-content", {
        duration: 0.8,
        opacity: 0,
        y: 20,
        ease: "power2.out",
        clearProps: "all"
    });

    // Animate elements with .animate-entry class
    gsap.utils.toArray('.animate-entry').forEach((element, i) => {
        gsap.from(element, {
            scrollTrigger: {
                trigger: element,
                start: "top 85%",
                toggleActions: "play none none reverse"
            },
            duration: 0.6,
            opacity: 0,
            y: 30,
            delay: i * 0.1,
            ease: "back.out(1.7)"
        });
    });

    // Hover effects for glass cards
    gsap.utils.toArray('.glass-card').forEach(card => {
        card.addEventListener('mouseenter', () => {
            gsap.to(card, { scale: 1.02, duration: 0.3, ease: "power1.out" });
        });
        card.addEventListener('mouseleave', () => {
            gsap.to(card, { scale: 1, duration: 0.3, ease: "power1.out" });
        });
    });
}
