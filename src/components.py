"""UI components and enhancements for the Fantasy Baseball Draft Tool."""

import streamlit as st



def inject_keyboard_shortcuts():
    """
    Inject JavaScript for keyboard shortcuts to focus search inputs.

    Shortcuts:
    - "/" key: Focus search input (when not typing in an input)
    - Ctrl+F / Cmd+F: Focus search input (overrides browser find)
    - Escape: Blur search input
    """
    js_code = """
    <script>
    (function() {
        // Prevent multiple injections
        if (window.keyboardShortcutsInjected) return;
        window.keyboardShortcutsInjected = true;

        function findSearchInput() {
            // Find search input by placeholder text
            const inputs = document.querySelectorAll('input[type="text"]');
            for (const input of inputs) {
                if (input.placeholder === 'Player name...') {
                    return input;
                }
            }
            return null;
        }

        function isTyping() {
            const active = document.activeElement;
            if (!active) return false;
            const tagName = active.tagName.toLowerCase();
            return tagName === 'input' || tagName === 'textarea' || active.isContentEditable;
        }

        document.addEventListener('keydown', function(e) {
            const searchInput = findSearchInput();

            // "/" key - focus search (only when not typing)
            if (e.key === '/' && !isTyping()) {
                if (searchInput) {
                    e.preventDefault();
                    searchInput.focus();
                    searchInput.select();
                }
            }

            // Ctrl+F or Cmd+F - focus search (override browser find)
            if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
                if (searchInput) {
                    e.preventDefault();
                    searchInput.focus();
                    searchInput.select();
                }
            }

            // Escape - blur search input
            if (e.key === 'Escape') {
                if (document.activeElement === searchInput) {
                    e.preventDefault();
                    searchInput.blur();
                }
            }
        });
    })();
    </script>
    """
    st.markdown(js_code, unsafe_allow_html=True)


def inject_keyboard_hint():
    """
    Inject CSS/HTML to show keyboard shortcut hint in bottom-right corner.

    The hint is hidden on mobile devices (screen width < 768px).
    """
    hint_html = """
    <style>
    .keyboard-hint {
        position: fixed;
        bottom: 16px;
        right: 16px;
        background-color: var(--sidebar-bg, rgba(27, 42, 74, 0.92));
        color: var(--sidebar-text, rgba(253, 246, 236, 0.85));
        padding: 8px 12px;
        border-radius: 6px;
        font-size: 12px;
        font-family: monospace;
        z-index: 1000;
        pointer-events: none;
        border: 1px solid rgba(196, 30, 58, 0.3);
        opacity: 0.92;
    }

    .keyboard-hint kbd {
        background-color: rgba(253, 246, 236, 0.15);
        padding: 2px 6px;
        border-radius: 3px;
        margin: 0 2px;
    }

    /* Hide on mobile devices */
    @media (max-width: 768px) {
        .keyboard-hint {
            display: none;
        }
    }
    </style>
    <div class="keyboard-hint">
        Quick search: <kbd>/</kbd> or <kbd>Ctrl+F</kbd>
    </div>
    """
    st.markdown(hint_html, unsafe_allow_html=True)
