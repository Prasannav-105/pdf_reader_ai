"""
styles.py: Modern Dark Theme CSS and Visual Design Tokens.
"""

DARK_THEME_CSS = """
<style>
    /* 1. Header & Sidebar Controls */
    header[data-testid="stHeader"] {
        background: transparent !important;
        height: 3.2rem !important;
        z-index: 100 !important;
    }

    /* Keep toolbar visible so Expand Sidebar Button is available */
    div[data-testid="stToolbar"] {
        visibility: visible !important;
        display: flex !important;
        background: transparent !important;
    }

    /* Make Expand Sidebar Button and Collapse Button prominent, styled & impossible to miss */
    [data-testid="stExpandSidebarButton"],
    button[data-testid="stSidebarCollapseButton"],
    [data-testid="stSidebarToggle"] {
        visibility: visible !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        color: #38BDF8 !important;
        background: #1E293B !important;
        border: 1.5px solid #4F46E5 !important;
        border-radius: 8px !important;
        padding: 6px 12px !important;
        margin: 6px !important;
        opacity: 1 !important;
        cursor: pointer !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4) !important;
    }
    [data-testid="stExpandSidebarButton"]:hover,
    button[data-testid="stSidebarCollapseButton"]:hover,
    [data-testid="stSidebarToggle"]:hover {
        background: #4F46E5 !important;
        border-color: #6366F1 !important;
        color: #FFFFFF !important;
    }

    /* Hide ONLY Deploy button and MainMenu (3-dots settings overlay that overlaps text) */
    #MainMenu {
        visibility: hidden !important;
        display: none !important;
    }
    .stDeployButton {
        display: none !important;
        visibility: hidden !important;
    }
    div[data-testid="stDecoration"] {
        visibility: hidden !important;
        display: none !important;
    }
    div[data-testid="stStatusWidget"] {
        visibility: hidden !important;
        display: none !important;
    }
    footer {
        visibility: hidden !important;
        display: none !important;
    }

    /* Dark Theme Core Tokens */
    :root {
        --bg-base: #090D16;
        --bg-surface: #111827;
        --bg-card: #1F2937;
        --bg-card-hover: #374151;
        --border-subtle: #374151;
        --border-highlight: #4F46E5;
        --text-primary: #F9FAFB;
        --text-secondary: #9CA3AF;
        --text-muted: #6B7280;
        --accent-emerald: #10B981;
        --accent-indigo: #6366F1;
        --accent-cyan: #06B6D4;
        --accent-amber: #F59E0B;
    }

    /* Overall Streamlit container adjustments */
    .stApp {
        background-color: var(--bg-base);
        color: var(--text-primary);
    }
    
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 3rem !important;
        max-width: 96% !important;
    }

    /* Modern Dark Cards */
    .dark-card {
        background-color: #161F30;
        border: 1px solid #28354A;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    }

    .dark-card:hover {
        border-color: #3B82F6;
    }

    /* Breadcrumbs */
    .breadcrumb-bar {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 10px 16px;
        background: #131C2E;
        border: 1px solid #233148;
        border-radius: 8px;
        margin-bottom: 16px;
        font-size: 0.9rem;
        color: #94A3B8;
    }

    .badge-page {
        background: #1E293B;
        color: #38BDF8;
        border: 1px solid #0284C7;
        padding: 2px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.8rem;
    }

    /* Textbook Excerpt Callout */
    .textbook-quote {
        background: #141C2B;
        border-left: 4px solid #38BDF8;
        padding: 14px 18px;
        border-radius: 0 8px 8px 0;
        margin: 18px 0;
        font-style: italic;
        color: #E2E8F0;
    }

    /* Key Takeaway Box */
    .takeaways-box {
        background: #0D2818;
        border: 1px solid #059669;
        border-radius: 8px;
        padding: 16px 20px;
        margin-top: 20px;
    }

    /* Quiz Container */
    .quiz-card {
        background: #181E2C;
        border: 1px solid #2C384E;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 14px;
    }

    /* Chat Drawer Styling */
    .chat-bubble-user {
        background: #312E81;
        color: #EEF2FF;
        padding: 12px 16px;
        border-radius: 12px 12px 2px 12px;
        margin-bottom: 10px;
        max-width: 85%;
        margin-left: auto;
    }

    .chat-bubble-ai {
        background: #1F2937;
        color: #F3F4F6;
        padding: 12px 16px;
        border-radius: 12px 12px 12px 2px;
        margin-bottom: 10px;
        border: 1px solid #374151;
        max-width: 85%;
    }

    /* Hardware Selector & Status Badge */
    .hardware-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: #1E293B;
        border: 1px solid #3B82F6;
        color: #93C5FD;
        padding: 6px 12px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-bottom: 8px;
    }

    .user-profile-badge {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: #131C2E;
        border: 1px solid #233148;
        padding: 8px 12px;
        border-radius: 8px;
        margin-bottom: 12px;
        color: #F1F5F9;
        font-size: 0.85rem;
    }
</style>
"""
