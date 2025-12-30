// 1. Define MockAuth globally first (No external dependencies needed)
const MockAuth = {
    currentUser: null,
    listeners: [],

    // Helper to access the "Fake Cloud" in browser storage
    _getUsersDB: () => JSON.parse(localStorage.getItem('local_users_db') || '{}'),
    _saveUsersDB: (db) => localStorage.setItem('local_users_db', JSON.stringify(db)),

    // 1. LOGIN (Strict Check)
    signInWithEmailAndPassword: async (auth, email, password) => {
        console.log(`🔌 LOCAL MODE: Attempting login for ${email}`);

        // Simulate network delay for realism
        await new Promise(r => setTimeout(r, 500));

        const db = MockAuth._getUsersDB();
        const userRecord = db[email];

        if (!userRecord) {
            const error = new Error("Firebase: Error (auth/user-not-found).");
            error.code = "auth/user-not-found";
            throw error;
        }

        if (userRecord.password !== password) {
            const error = new Error("Firebase: Error (auth/wrong-password).");
            error.code = "auth/wrong-password";
            throw error;
        }

        // Login Successful
        const user = {
            uid: userRecord.uid,
            email: userRecord.email,
            displayName: email.split('@')[0],
            getIdToken: async () => userRecord.uid // Token is the UID
        };

        MockAuth._setCurrentUser(user);
        return { user };
    },

    // 2. SIGN UP (Create New)
    createUserWithEmailAndPassword: async (auth, email, password) => {
        console.log(`🔌 LOCAL MODE: Creating account for ${email}`);

        await new Promise(r => setTimeout(r, 500));

        const db = MockAuth._getUsersDB();

        if (db[email]) {
            const error = new Error("Firebase: Error (auth/email-already-in-use).");
            error.code = "auth/email-already-in-use";
            throw error;
        }

        // Generate a unique ID based on email
        const newUid = "local_" + email.split('@')[0].replace(/[^a-z0-9]/gi, '') + "_" + Date.now().toString().slice(-4);

        // Save to "Browser Database"
        db[email] = {
            uid: newUid,
            email: email,
            password: password // Stored locally for mock auth check
        };
        MockAuth._saveUsersDB(db);

        // Auto-login after signup
        const user = {
            uid: newUid,
            email: email,
            displayName: email.split('@')[0],
            getIdToken: async () => newUid
        };

        MockAuth._setCurrentUser(user);
        return { user };
    },

    // 3. GOOGLE LOGIN (Simulated - always logs in as specific demo user)
    signInWithPopup: async (auth, provider) => {
        console.log("🔌 LOCAL MODE: Simulating Google Login");
        const email = "demo_google@local.com";
        const db = MockAuth._getUsersDB();

        // Auto-create if not exists (Google usually behaves this way)
        if (!db[email]) {
            await MockAuth.createUserWithEmailAndPassword(null, email, "google-pass");
        }
        return MockAuth.signInWithEmailAndPassword(null, email, "google-pass");
    },

    // 4. LOGOUT
    signOut: async (auth) => {
        console.log("🔌 LOCAL MODE: Signing out");
        localStorage.removeItem('local_current_session');
        MockAuth.currentUser = null;
        MockAuth.triggerAuth(null);
    },

    // 5. STATE OBSERVER
    onAuthStateChanged: (auth, callback) => {
        MockAuth.listeners.push(callback);

        // Check if a user was logged in previously
        const storedSession = localStorage.getItem('local_current_session');
        if (storedSession) {
            try {
                const user = JSON.parse(storedSession);
                user.getIdToken = async () => user.uid; // Re-attach function
                MockAuth.currentUser = user;
                callback(user);
            } catch (e) {
                callback(null);
            }
        } else {
            callback(null);
        }
    },

    // Internal Helpers
    _setCurrentUser: (user) => {
        MockAuth.currentUser = user;
        // Save session
        localStorage.setItem('local_current_session', JSON.stringify(user));
        MockAuth.triggerAuth(user);
    },

    triggerAuth: (user) => {
        MockAuth.listeners.forEach(cb => cb(user));
    }
};

// 2. Main Initialization Function
async function initializeAppLogic() {
    try {
        // Fetch Config
        const response = await fetch('/api/config');
        if (!response.ok) throw new Error("Failed to fetch config");
        const config = await response.json();

        // Store globally for AlpineJS components
        window.APP_CONFIG = config;

        // === LOCAL MODE ===
        if (config.dbMode === 'LOCAL') {
            console.log("🔶 RUNNING IN LOCAL DATABASE MODE (Offline-Ready)");

            // Define Global Objects for AlpineJS
            window.firebaseAuth = {};
            window.firebaseAnalytics = {};

            // Map Mock functions to the global window object
            window.firebaseAuthFunctions = {
                createUserWithEmailAndPassword: MockAuth.createUserWithEmailAndPassword,
                signInWithEmailAndPassword: MockAuth.signInWithEmailAndPassword,
                onAuthStateChanged: MockAuth.onAuthStateChanged,
                signOut: MockAuth.signOut,
                setPersistence: async () => { },
                browserLocalPersistence: "local",
                GoogleAuthProvider: class { },
                signInWithPopup: MockAuth.signInWithPopup,
                sendPasswordResetEmail: async () => alert("Local Mode: Password reset simulated."),
                sendEmailVerification: async () => console.log("Local Mode: Email verification simulated.")
            };

            // Logging wrapper
            window.logAnalyticsEvent = (name, params) => console.log(`[Analytics] ${name}`, params);

            // Trigger initial auth check
            MockAuth.onAuthStateChanged(null, (user) => {
                console.log("Local Auth State Checked:", user ? "Logged In" : "Logged Out");
            });

        }
        // === CLOUD MODE ===
        else {
            console.log("☁️ RUNNING IN FIREBASE CLOUD MODE - Loading SDKs...");

            // DYNAMIC IMPORTS: Only load these if we are in Cloud Mode
            const firebaseApp = await import("https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js");
            const firebaseAuth = await import("https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js");
            const firebaseAnalytics = await import("https://www.gstatic.com/firebasejs/10.7.1/firebase-analytics.js");

            const app = firebaseApp.initializeApp(config.firebaseConfig);
            const auth = firebaseAuth.getAuth(app);
            const analytics = firebaseAnalytics.getAnalytics(app);

            // Expose to window
            window.firebaseAuth = auth;
            window.firebaseAnalytics = analytics;

            // Map Real Firebase functions to window
            window.firebaseAuthFunctions = {
                createUserWithEmailAndPassword: firebaseAuth.createUserWithEmailAndPassword,
                signInWithEmailAndPassword: firebaseAuth.signInWithEmailAndPassword,
                onAuthStateChanged: firebaseAuth.onAuthStateChanged,
                signOut: firebaseAuth.signOut,
                setPersistence: firebaseAuth.setPersistence,
                browserLocalPersistence: firebaseAuth.browserLocalPersistence,
                GoogleAuthProvider: firebaseAuth.GoogleAuthProvider,
                signInWithPopup: firebaseAuth.signInWithPopup,
                sendEmailVerification: firebaseAuth.sendEmailVerification,
                sendPasswordResetEmail: firebaseAuth.sendPasswordResetEmail
            };

            window.logAnalyticsEvent = (eventName, params) => firebaseAnalytics.logEvent(analytics, eventName, params);

            console.log("✅ Firebase Cloud SDK Loaded");
        }

    } catch (error) {
        console.error('❌ Critical Initialization Error:', error);
        alert("Failed to initialize application. Check console.");
    }
}

// Start the app
initializeAppLogic();

let API_BASE_URL = ""; // Will be set by loadConfig

async function loadConfig() {
    if (window.APP_CONFIG) {
        API_BASE_URL = window.APP_CONFIG.apiBaseUrl;
        return window.APP_CONFIG;
    }
    // Fallback if loadConfig is called before init logic (shouldn't happen often)
    try {
        const response = await fetch('/api/config');
        const config = await response.json();
        window.APP_CONFIG = config;
        API_BASE_URL = config.apiBaseUrl;
        console.log('API Base URL loaded (Fallback):', API_BASE_URL);
        return config;
    } catch (error) {
        console.error('Failed to load API config:', error);
        API_BASE_URL = "";
        return { dbMode: 'LOCAL' }; // Safe fallback
    }
}

// --- Static Data (Defined globally for scope access) ---
const NIFTY_50_STOCKS_GLOBAL = ['RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'INFY.NS', 'HINDUNILVR.NS', 'BHARTIARTL.NS', 'ITC.NS', 'SBIN.NS', 'LICI.NS', 'HCLTECH.NS', 'KOTAKBANK.NS', 'LT.NS', 'BAJFINANCE.NS', 'AXISBANK.NS', 'ASIANPAINT.NS', 'MARUTI.NS', 'SUNPHARMA.NS', 'TITAN.NS', 'WIPRO.NS', 'ULTRACEMCO.NS', 'ADANIENT.NS', 'ONGC.NS', 'NTPC.NS', 'JSWSTEEL.NS', 'TATAMOTORS.NS', 'POWERGRID.NS', 'BAJAJFINSV.NS', 'TATASTEEL.NS', 'COALINDIA.NS', 'INDUSINDBK.NS', 'HINDALCO.NS', 'TECHM.NS', 'GRASIM.NS', 'ADANIPORTS.NS', 'BRITANNIA.NS', 'CIPLA.NS', 'EICHERMOT.NS', 'DRREDDY.NS', 'NESTLEIND.NS', 'HEROMOTOCO.NS', 'BAJAJ-AUTO.NS', 'BPCL.NS', 'SHREECEM.NS', 'TATACONSUM.NS', 'UPL.NS', 'APOLLOHOSP.NS', 'DIVISLAB.NS'];

const COMPANY_NAMES_GLOBAL = {
    'RELIANCE.NS': 'Reliance Industries', 'TCS.NS': 'Tata Consultancy Services', 'HDFCBANK.NS': 'HDFC Bank', 'ICICIBANK.NS': 'ICICI Bank', 'INFY.NS': 'Infosys', 'HINDUNILVR.NS': 'Hindustan Unilever', 'BHARTIARTL.NS': 'Bharti Airtel', 'ITC.NS': 'ITC Limited', 'SBIN.NS': 'State Bank of India', 'LICI.NS': 'Life Insurance Corp', 'HCLTECH.NS': 'HCL Technologies', 'KOTAKBANK.NS': 'Kotak Mahindra Bank', 'LT.NS': 'Larsen & Toubro', 'BAJFINANCE.NS': 'Bajaj Finance', 'AXISBANK.NS': 'Axis Bank', 'ASIANPAINT.NS': 'Asian Paints', 'MARUTI.NS': 'Maruti Suzuki', 'SUNPHARMA.NS': 'Sun Pharma', 'TITAN.NS': 'Titan Company', 'WIPRO.NS': 'Wipro', 'ULTRACEMCO.NS': 'UltraTech Cement', 'ADANIENT.NS': 'Adani Enterprises', 'ONGC.NS': 'Oil & Natural Gas', 'NTPC.NS': 'NTPC Limited', 'JSWSTEEL.NS': 'JSW Steel', 'TATAMOTORS.NS': 'Tata Motors', 'POWERGRID.NS': 'Power Grid Corp', 'BAJAJFINSV.NS': 'Bajaj Finserv', 'TATASTEEL.NS': 'Tata Steel', 'COALINDIA.NS': 'Coal India', 'INDUSINDBK.NS': 'IndusInd Bank', 'HINDALCO.NS': 'Hindalco Industries', 'TECHM.NS': 'Tech Mahindra', 'GRASIM.NS': 'Grasim Industries', 'ADANIPORTS.NS': 'Adani Ports', 'BRITANNIA.NS': 'Britannia Industries', 'CIPLA.NS': 'Cipla', 'EICHERMOT.NS': 'Eicher Motors', 'DRREDDY.NS': 'Dr. Reddys Labs', 'NESTLEIND.NS': 'Nestle India', 'HEROMOTOCO.NS': 'Hero MotoCorp', 'BAJAJ-AUTO.NS': 'Bajaj Auto', 'BPCL.NS': 'Bharat Petroleum', 'SHREECEM.NS': 'Shree Cement', 'TATACONSUM.NS': 'Tata Consumer', 'UPL.NS': 'UPL Limited', 'APOLLOHOSP.NS': 'Apollo Hospitals', 'DIVISLAB.NS': 'Divis Laboratories'
};

function chatApp() {
    // --- Component State ---
    return {
        selectedIndicators: ['rsi', 'ema', 'sma'], // Default selected
        availableIndicators: [
            { id: 'rsi', name: 'RSI', description: 'Relative Strength Index (14)' },
            { id: 'ema', name: 'EMA', description: 'Exponential Moving Average (20)' },
            { id: 'sma', name: 'SMA', description: 'Simple Moving Average (50)' }
        ],
        isLoggedIn: false,
        isLoginView: false,
        isLoading: false,
        email: '',
        password: '',
        confirmPassword: '',
        authError: '',
        currentUser: null,
        showForgotPassword: false,
        resetEmail: '',
        resetSuccess: false,
        resetError: '',

        resetError: '',

        suppressAuthRedirect: false,
        verificationModalOpen: false,

        mobileSidebarOpen: false,
        isSidebarMinimized: true,
        currentChatId: null,
        chatList: [],
        chatLoading: false,

        // Search State
        searchVisible: false,
        searchQuery: '',
        searchResults: [], // Will store the highlighted <mark> elements
        currentSearchResultIndex: -1,
        isLocalMode: false,

        portfolioOpen: false,
        portfolioMinimized: false,
        portfolioMaximized: false,
        portfolioTab: 'portfolio',
        portfolio: { cash: 0, holdings: [], summary: {} },
        watchlist: [],
        tradeHistory: [],
        portfolioLoading: false,
        portfolioLastUpdated: null,
        lastUpdatedText: 'never',
        reloadIntervalId: null,

        cashEditModalOpen: false,
        newCashAmount: 0,

        isChatsLoading: false, // New state for chat loading spinner

        renameModalOpen: false,
        chatToRename: { id: null, title: '' },
        newChatTitle: '',

        stockPickerOpen: false,
        stockPickerMode: 'trade',
        selectedStock: '',
        selectedStocks: [],
        stockSearch: '',
        filteredStocks: NIFTY_50_STOCKS_GLOBAL, // Initialize with global list

        tradeModalOpen: false,
        tradeAction: 'BUY',
        tradeTicker: '',
        tradeQuantity: 1,
        tradeError: '',
        tradeLoading: false,
        selectedTimeframe: '1D',
        currentStockPrice: 0,
        totalTradeValue: 0,
        loadingPrice: false,
        loadingPrice: false,
        tokenUsage: { input: 0, output: 0, total: 0 },
        currentPlan: 'Free Tier', // Default
        tokensLeft: 0,
        tokenLimit: 0,
        editName: '',

        analysisModalOpen: false,
        analysisLoading: false,
        analysisData: { indicators: {} }, // IMPORTANT: Initialize indicators object

        // New Zerodha Sync State
        zerodhaSynced: false,
        zerodhaSyncMessage: 'Not connected. Sync your Zerodha holdings.',
        zerodhaSyncLoading: false,

        async secureFetch(url, options = {}) {
            if (!this.currentUser) {
                console.error("Auth Error: No user logged in.");
                this.authError = "You are not logged in. Please refresh.";
                this.handleLogout(); // Force logout
                return Promise.reject(new Error("User not authenticated"));
            }

            try {
                const token = await this.currentUser.getIdToken(true);
                const headers = new Headers(options.headers || {});
                headers.set('Authorization', `Bearer ${token}`);

                const secureOptions = {
                    ...options,
                    headers: headers
                };

                const response = await fetch(url, secureOptions);

                if (response.status === 401) {
                    console.error("Auth Error: Server rejected token.");
                    this.authError = "Your session has expired. Please log in again.";
                    this.handleLogout(); // Force logout
                    return Promise.reject(new Error("Token rejected by server"));
                }

                // 403 is now passed through for logic handling (e.g. Token Limit)
                return response;

            } catch (error) {
                console.error("Error in secureFetch:", error);
                this.authError = "Could not verify your session. Please log in again.";
                this.handleLogout();
                return Promise.reject(error);
            }
        },

        async updateProfile() {
            if (!this.editName.trim()) return;

            if (this.currentUser) {
                this.currentUser.displayName = this.editName;
            }
            if (this.isLocalMode) {
                const stored = JSON.parse(localStorage.getItem('local_user') || '{}');
                stored.displayName = this.editName;
                localStorage.setItem('local_user', JSON.stringify(stored));
                const db = JSON.parse(localStorage.getItem('local_users_db') || '{}');
                if (this.currentUser.email && db[this.currentUser.email]) {
                    db[this.currentUser.email].displayName = this.editName;
                    localStorage.setItem('local_users_db', JSON.stringify(db));
                }
                alert("Name updated successfully!");
            } else {
                alert("Name updated for this session.");
            }
        },

        async init() {
            // Check for global config first
            if (window.APP_CONFIG) {
                this.isLocalMode = (window.APP_CONFIG.dbMode === 'LOCAL');
            } else {
                const conf = await loadConfig(); // Fallback fetch
                if (conf) this.isLocalMode = (conf.dbMode === 'LOCAL');
            }

            // Wait for Firebase Functions to be attached to window
            const checkFirebase = setInterval(() => {
                if (window.firebaseAuthFunctions) {
                    clearInterval(checkFirebase);
                    this.initFirebase();
                }
            }, 50);

            if (window.location.search.includes('sync=success')) {
                window.history.replaceState({}, document.title, window.location.pathname);
            }
        },

        formatNumber(num) {
            if (!num && num !== 0) return '0';
            if (typeof num === 'string') return num;
            return num.toLocaleString('en-IN');
        },

        formatCost(input, output) {
            // Safety check if config isn't loaded yet
            if (!window.APP_CONFIG || !window.APP_CONFIG.geminiPrices) return '0.00';

            const prices = window.APP_CONFIG.geminiPrices;

            // Input: per 1 million
            const inputCost = (input / 1000000) * prices.inputPerMillion;
            // Output: per 1 million
            const outputCost = (output / 1000000) * prices.outputPerMillion;

            const totalUsd = inputCost + outputCost;
            const totalInr = totalUsd * prices.inrRate;

            // Show 4 decimals if < 0.01, else 2
            if (totalInr > 0 && totalInr < 0.01) {
                return totalInr.toFixed(4);
            }
            return totalInr.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        },

        async initFirebase() {
            await new Promise(resolve => {
                const checkFirebase = setInterval(() => {
                    if (window.firebaseAuth && window.firebaseAuthFunctions) {
                        clearInterval(checkFirebase);
                        resolve();
                    }
                }, 50);
            });

            const { onAuthStateChanged, setPersistence, browserLocalPersistence } = window.firebaseAuthFunctions;
            await setPersistence(window.firebaseAuth, browserLocalPersistence);

            onAuthStateChanged(window.firebaseAuth, user => {
                if (user) {
                    // Fix for flicker: Don't log in if we are in the middle of a signup flow that will immediately sign out
                    if (this.suppressAuthRedirect) {
                        console.log("Suppressing auth redirect (Signup in progress)");
                        return;
                    }

                    this.isLoggedIn = true;
                    this.currentUser = user;
                    this.loadInitialData();
                } else {
                    this.isLoggedIn = false;
                    this.currentUser = null;
                    if (this.reloadIntervalId) clearInterval(this.reloadIntervalId);
                }
                document.body.classList.remove('auth-loading');
            });
        },

        async loadInitialData() {
            await this.fetchChatList();

            if (this.chatList.length > 0) {
                this.loadChat(this.chatList[0].chatId, true);
            } else {
                this.startNewChat(true);
            }
            await this.loadPortfolio();

        },

        async getProactiveAlert() {
            console.log("Checking for proactive alerts...");
            // Placeholder for future implementation
        },

        async handleSignup() {
            if (this.password !== this.confirmPassword) {
                this.authError = "Passwords do not match";
                return;
            }
            this.isLoading = true;
            this.authError = '';
            try {

                // Set flag to prevent onAuthStateChanged from triggering "Login" state
                this.suppressAuthRedirect = true;

                const { user } = await window.firebaseAuthFunctions.createUserWithEmailAndPassword(window.firebaseAuth, this.email, this.password);

                if (!this.isLocalMode) {
                    await window.firebaseAuthFunctions.sendEmailVerification(user);
                    await window.firebaseAuthFunctions.signOut(window.firebaseAuth);

                    // Reset flag after signout is complete
                    this.suppressAuthRedirect = false;

                    // Show custom modal instead of alert
                    this.verificationModalOpen = true;
                    // Do NOT navigate to login view immediately; the modal "Back to Login" button handles that
                    this.authError = '';
                    return;
                }
            } catch (error) {
                this.authError = error.message.replace('Firebase: ', '');
            } finally {
                this.isLoading = false;
            }
        },

        async signInWithGoogle() {
            this.isLoading = true;
            this.authError = '';
            try {
                const { GoogleAuthProvider, signInWithPopup } = window.firebaseAuthFunctions;
                const provider = new GoogleAuthProvider();
                await signInWithPopup(window.firebaseAuth, provider);
            } catch (error) {
                this.authError = error.message.replace('Firebase: ', '');
            } finally {
                this.isLoading = false;
            }
        },

        async handleForgotPassword() {
            this.isLoading = true;
            this.resetError = '';
            this.resetSuccess = false;
            try {
                const { sendPasswordResetEmail } = window.firebaseAuthFunctions;
                await sendPasswordResetEmail(window.firebaseAuth, this.resetEmail);
                this.resetSuccess = true;
                setTimeout(() => {
                    this.showForgotPassword = false;
                    this.resetEmail = '';
                    this.resetSuccess = false;
                }, 3000);
            } catch (error) {
                this.resetError = error.message.replace('Firebase: ', '');
            } finally {
                this.isLoading = false;
            }
        },

        async handleLogin() {
            this.isLoading = true;
            this.authError = '';
            try {
                const { user } = await window.firebaseAuthFunctions.signInWithEmailAndPassword(window.firebaseAuth, this.email, this.password);

                if (!this.isLocalMode && !user.emailVerified) {
                    await window.firebaseAuthFunctions.signOut(window.firebaseAuth);
                    this.authError = "Please verify your email first.";
                    return;
                }
            } catch (error) {
                this.authError = error.message.replace('Firebase: ', '');
            } finally {
                this.isLoading = false;
            }
        },

        async handleLogout() {
            await window.firebaseAuthFunctions.signOut(window.firebaseAuth);
        },

        async fetchChatList() {
            // this.isChatsLoading = true; // Optional: If specific sidebar loading needed
            try {
                const response = await this.secureFetch(`${API_BASE_URL}/api/chats/${this.currentUser.uid}`);
                if (response.ok) this.chatList = await response.json();
            } catch (error) {
                console.error("Error fetching chat list:", error);
            }
        },

        // loadChat has been moved to later in the file to resolve duplication

        async startNewChat(showAlert = false) {
            this.currentChatId = null;
            this.clearSearch();
            this.searchVisible = false;
            this.mobileSidebarOpen = false;
            document.getElementById('chat-title').textContent = "New Chat";
            document.getElementById('message-container').innerHTML = '';

            if (showAlert) await this.getProactiveAlert();

            this.appendMessage("Hello! I'm your Claroz Agent. How can I help you today?", 'agent');
            this.$nextTick(() => document.getElementById('message-input')?.focus());
        },

        async deleteChat(chatId) {
            try {
                const response = await this.secureFetch(`${API_BASE_URL}/api/chat/${this.currentUser.uid}/${chatId}`, { method: 'DELETE' });
                if (response.ok) {
                    await this.fetchChatList();
                    if (this.currentChatId === chatId) {
                        if (this.chatList.length > 0) {
                            this.loadChat(this.chatList[0].chatId);
                        } else {
                            this.startNewChat();
                        }
                    }
                }
            } catch (e) {
                this.appendMessage('Error: Could not delete chat.', 'system');
            }
        },

        openRenameModal(chatId, currentTitle) {
            this.chatToRename.id = chatId;
            this.chatToRename.title = currentTitle;
            this.newChatTitle = currentTitle;
            this.renameModalOpen = true;
            this.$nextTick(() => this.$refs.renameInput.focus());
        },

        async submitRename() {
            if (!this.newChatTitle || !this.chatToRename.id || this.newChatTitle.trim() === '') return;

            try {
                const response = await this.secureFetch(`${API_BASE_URL}/api/chat/${this.currentUser.uid}/${this.chatToRename.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title: this.newChatTitle.trim() })
                });
                if (response.ok) {
                    await this.fetchChatList();
                    if (this.currentChatId === this.chatToRename.id) {
                        document.getElementById('chat-title').textContent = this.newChatTitle.trim();
                    }
                }
            } catch (e) {
                this.appendMessage('Error: Could not rename chat.', 'system');
            } finally {
                this.renameModalOpen = false;
            }
        },

        // --- START: ANALYSIS MODAL LOGIC ---

        async openAnalysisModal(ticker) {
            this.analysisModalOpen = true;
            this.selectedTimeframe = '1D'; // Reset to default

            // Fix Blinking: Only reset if it's a DIFFERENT ticker
            if (!this.analysisData || this.analysisData.ticker !== ticker) {
                this.analysisData = { ticker: ticker, companyName: 'Loading...', indicators: {} };
            }

            await this.loadAnalysisData(ticker); // Call the correct function
        },

        async loadAnalysisData(ticker) {
            // Show loading state
            this.analysisLoading = true;

            console.log(`Loading analysis for ${ticker} with timeframe ${this.selectedTimeframe}`);

            try {
                const indicatorsParam = this.selectedIndicators.join(',');
                const url = `${API_BASE_URL}/api/stock/analysis/${this.currentUser.uid}/${ticker}?timeframe=${this.selectedTimeframe}&indicators=${indicatorsParam}`;
                console.log("Fetching from URL:", url);

                const response = await this.secureFetch(url);
                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.error || 'Failed to fetch data');
                }

                const data = await response.json();
                console.log("Analysis data received:", data);

                // Update data smoothly without hiding the modal
                this.analysisData = data;

            } catch (error) {
                console.error("Analysis modal error:", error);
                this.analysisData = {
                    companyName: 'Error',
                    ticker: ticker,
                    currentPrice: 'N/A',
                    recommendation: 'N/A',
                    technicalRating: 'N/A',
                    targetPrice: 'N/A',
                    peRatio: 'N/A',
                    pbRatio: 'N/A',
                    dividendYield: 'N/A',
                    marketCap: 'N/A',
                    indicators: {}
                };
            } finally {
                this.analysisLoading = false;
                this.updateDynamicTechnicalRating();
            }
        },

        parseMarkdown(text) {
            if (!text) return '';

            // 1. Handle Lists (Replace * or - with •)
            let formatted = text.replace(/^[\*\-] (.*)/gm, '• $1');

            // 2. Handle Bold (**text**) -> RESTORED TO GREEN HERE
            formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<span class="font-bold text-green-400">$1</span>');

            // 3. Handle Headers (### text)
            formatted = formatted.replace(/^### (.*)/gm, '<h3 class="text-sm font-bold text-green-400 mt-3 mb-1 uppercase tracking-wide">$1</h3>');

            // 4. Handle Links [Text](Url)
            formatted = formatted.replace(/\[([^\]]+)\]\((http[s]?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank" class="text-emerald-400 hover:text-emerald-500 hover:underline transition-colors">$1</a>');

            // 5. Handle Line Breaks
            return formatted.split('\n').map(line => {
                if (line.trim() === '') return '<br>';
                return `<div class="min-h-[20px]">${line}</div>`;
            }).join('');
        },

        updateDynamicTechnicalRating() {
            if (!this.analysisData.indicators) {
                this.analysisData.technicalRating = "N/A";
                return;
            }

            if (this.selectedIndicators.length === 0) {
                this.analysisData.technicalRating = "Neutral"; // As you wanted
                return;
            }

            let score = 0;
            let maxScore = 0;
            const raw = this.analysisData.indicators;

            this.selectedIndicators.forEach(id => {
                let value = raw[id];
                if (value === 'N/A' || value === undefined || value === null) return;

                try {
                    if (id === 'rsi') {
                        maxScore += 10;
                        if (value < 30) score += 10;      // Strong Buy
                        else if (value < 45) score += 7;  // Buy
                        else if (value > 75) score += 0;  // Strong Sell
                        else if (value > 60) score += 3;  // Sell
                        else score += 5;                  // Neutral
                    }
                    else if (id === 'ema' || id === 'sma') {
                        let price = parseFloat(this.analysisData.currentPrice.replace('₹', ''));
                        if (isNaN(price)) return;
                        maxScore += 10;
                        if (price > value) score += 9; // Buy
                        else if (price < value) score += 1; // Sell
                    }
                } catch (e) {
                    console.error(`Error scoring ${id}:`, e);
                }
            });

            if (maxScore === 0) {
                this.analysisData.technicalRating = (this.selectedIndicators.length > 0) ? "N/A" : "Neutral";
                return;
            }

            const finalPercentage = (score / maxScore) * 100;

            if (finalPercentage >= 75) this.analysisData.technicalRating = "Strong Buy";
            else if (finalPercentage >= 60) this.analysisData.technicalRating = "Buy";
            else if (finalPercentage >= 40) this.analysisData.technicalRating = "Neutral";
            else if (finalPercentage >= 25) this.analysisData.technicalRating = "Sell";
            else this.analysisData.technicalRating = "Strong Sell";

            console.log(`Dynamic Rating: ${this.analysisData.technicalRating} (Score: ${finalPercentage.toFixed(1)}%) based on:`, this.selectedIndicators);
        },

        getIndicatorName(id) {
            const indicator = this.availableIndicators.find(ind => ind.id === id);
            return indicator ? indicator.name : id.toUpperCase();
        },

        // THIS IS THE FIX for empty boxes
        getIndicatorValue(id) {
            if (!this.analysisData.indicators || this.analysisData.indicators[id] === undefined || this.analysisData.indicators[id] === null) {
                return 'N/A';
            }

            let value = this.analysisData.indicators[id];
            if (value === 'N/A') return 'N/A';

            try {
                if (id === 'volume') {
                    if (value > 1000000) return (value / 1000000).toFixed(2) + 'M';
                    if (value > 1000) return (value / 1000).toFixed(2) + 'K';
                    return value.toString();
                }
                if (id === 'bollinger') {
                    return value.toString();
                }
                if (typeof value === 'number') {
                    return value.toFixed(2);
                }
                return value.toString();

            } catch (e) {
                console.error(`Error formatting ${id}:`, e);
                return 'N/A';
            }
        },

        getTechnicalAngle(rating) {
            if (!rating || rating === 'N/A') return 0; // Center position
            const r = rating.toLowerCase();

            if (r.includes('strong') && r.includes('sell')) return -80;
            if (r.includes('sell')) return -40;
            if (r.includes('neutral') || r.includes('hold')) return 0;
            if (r.includes('buy') && !r.includes('strong')) return 40;
            if (r.includes('strong') && r.includes('buy')) return 80;
            return 0;
        },

        getAnalystAngle(recommendation) {
            if (!recommendation || recommendation === 'N/A') return 0;
            const rec = recommendation.toLowerCase();

            if (rec.includes('strong') && rec.includes('sell')) return -80;
            if (rec.includes('sell') && !rec.includes('strong')) return -40;
            if (rec.includes('hold') || rec.includes('neutral')) return 0;
            if (rec.includes('buy') && !rec.includes('strong')) return 40;
            if (rec.includes('strong') && rec.includes('buy')) return 80;
            return 0;
        },

        // --- END: ANALYSIS MODAL LOGIC ---

        async sendMessage() {
            const input = document.getElementById('message-input');
            const message = input.value.trim();
            if (!message) return;

            this.appendMessage(message, 'user');
            input.value = '';
            this.autoResize(input);

            const typingId = Date.now();
            this.appendTypingIndicator(typingId);

            const sendButton = document.getElementById('send-button');
            if (sendButton) sendButton.disabled = true;
            if (input) input.disabled = true;

            try {
                const response = await this.secureFetch(`${API_BASE_URL}/api/chat`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        userId: this.currentUser.uid,
                        chatId: this.currentChatId,
                        message: message
                    })
                });

                const data = await response.json();
                document.getElementById(`typing-${typingId}`)?.remove();

                if (response.ok) {
                    // 1. Show Message
                    this.appendMessage(data.reply, 'agent', true, data);

                    // 2. LIVE UPDATE TOKEN STATS
                    if (data.tokenUsage) {
                        // Ensure object exists
                        if (!this.tokenUsage) this.tokenUsage = { input: 0, output: 0, total: 0 };

                        // Add the new cost to the existing Total
                        this.tokenUsage.input += (data.tokenUsage.inputTokens || 0);
                        this.tokenUsage.output += (data.tokenUsage.outputTokens || 0);
                        this.tokenUsage.total += (data.tokenUsage.totalTokens || 0);
                    }

                    if (!this.currentChatId && data.chatId) {
                        this.currentChatId = data.chatId;
                        await this.fetchChatList();
                        const newChat = this.chatList.find(c => c.chatId === data.chatId);
                        if (newChat) document.getElementById('chat-title').textContent = newChat.title;
                    }
                } else if (response.status === 403 && data.error === "TOKEN_LIMIT_EXCEEDED") {
                    // Handle Token Limit Exceeded specifically
                    this.appendMessage(`⚠️ ${data.message} Reset in ${data.days_remaining} day(s).`, 'system');
                } else {
                    this.appendMessage(`Sorry, an error occurred: ${data.error || 'Unknown error'}`, 'system');
                }
            } catch (error) {
                document.getElementById(`typing-${typingId}`)?.remove();
                if (error.message !== "Token rejected by server" && error.message !== "User not authenticated") {
                    this.appendMessage('Network error. Please try again.', 'system');
                }
            } finally {
                if (sendButton) sendButton.disabled = false;
                if (input) {
                    input.disabled = false;
                    input.focus();
                }
            }
        },

        appendMessage(text, sender, animate = true, metadata = null) {
            const container = document.getElementById('message-container');
            const div = document.createElement('div');
            const welcome = document.getElementById('welcome-screen');
            if (welcome) welcome.style.display = 'none';

            const isUser = sender === 'user';
            const isSystem = sender === 'system';

            // Layout
            div.className = `flex w-full ${isUser ? 'justify-end' : 'justify-start'} ${animate ? 'animate-slide-in' : ''}`;

            if (isUser) {
                div.innerHTML = `
                            <div class="message-user max-w-[85%] sm:max-w-[70%] bg-emerald-600 text-white px-5 py-3.5 rounded-2xl rounded-tr-none shadow-lg shadow-emerald-900/20 border border-white/10">
                                <p class="text-sm leading-relaxed whitespace-pre-wrap font-medium">${text}</p>
                            </div>
                        `;
            } else if (!isSystem) {
                let formattedText = this.parseMarkdown(text);

                // --- SIMPLE LINK FIX ---
                // Just a clean blue/green link. No buttons, no boxes.
                formattedText = formattedText.replace(
                    /<a href="(https:\/\/www\.tradingview\.com\/chart.*?)"(.*?)>.*?<\/a>/g,
                    `<a href="$1" $2 target="_blank" class="inline-flex items-center gap-1.5 text-emerald-400 hover:text-emerald-300 hover:underline font-medium mt-1 transition-colors">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                                View Chart
                             </a>`
                );

                // Thinking Process (Kept functionality, minimal style)
                let thoughtProcessHtml = '';
                if (metadata && (metadata.toolsUsed?.length > 0 || metadata.tokenUsage)) {
                    const totalTokens = metadata.tokenUsage?.totalTokens || 0;

                    thoughtProcessHtml = `
                            <div x-data="{ expanded: false }" class="mb-2">
                                <button @click="expanded = !expanded" class="flex items-center gap-2 text-[10px] font-bold text-slate-500 hover:text-slate-300 transition-colors uppercase tracking-wider">
                                    <div class="w-1.5 h-1.5 rounded-full bg-slate-600"></div>
                                    <span>Process</span>
                                    <svg class="w-3 h-3 transition-transform duration-200" :class="expanded ? 'rotate-180' : ''" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>
                                </button>
                                
                                <div x-show="expanded" x-collapse class="mt-1 pl-2 border-l-2 border-slate-800 space-y-1 text-xs text-slate-400">
                                    ${metadata.toolsUsed?.length ? `<div class="font-mono text-[10px]">Tools: ${metadata.toolsUsed.join(', ')}</div>` : ''}
                                    ${metadata.tokenUsage ? `<div class="font-mono text-[10px]">Tokens: ${metadata.tokenUsage.totalTokens}</div>` : ''}
                                </div>
                            </div>`;
                }

                div.innerHTML = `
                            <div class="agent-msg-container flex gap-3 w-full max-w-4xl group">
                                <div class="w-8 h-8 rounded-lg bg-slate-800 flex-shrink-0 flex items-center justify-center border border-slate-700 mt-1">
                                    <svg class="w-5 h-5 text-emerald-500" fill="currentColor" viewBox="0 0 24 24"><path d="M3.5 18.49l6-6.01 4 4L22 6.92l-1.41-1.41-7.09 7.97-4-4L2 16.99z" /></svg>
                                </div>
                                
                                <div class="flex-1 min-w-0">
                                    <div class="flex items-center justify-between mb-1">
                                        <p class="text-[10px] font-bold text-slate-500 uppercase">Claroz Agent</p>
                                    </div>
                                    
                                    ${thoughtProcessHtml}
                                    
                                    <div class="text-slate-200 text-sm leading-7 tracking-wide break-words whitespace-pre-wrap">${formattedText}</div>
                                </div>
                            </div>
                        `;
            } else {
                // System Message
                div.innerHTML = `<div class="mx-auto my-4 px-4 py-1.5 bg-slate-800/50 border border-slate-700 rounded-full text-[11px] text-slate-400 font-medium text-center">${text}</div>`;
            }

            container.appendChild(div);
            this.scrollToBottom();
        },

        appendTypingIndicator(id) {
            const container = document.getElementById('message-container');
            const div = document.createElement('div');
            div.id = `typing-${id}`;
            div.className = 'message flex justify-start';
            div.innerHTML = `
                      <div class="message-agent px-4 py-3 shadow-lg">
                          <div class="flex gap-1">
                              <div class="w-2 h-2 bg-slate-500 rounded-full typing-dot"></div>
                              <div class="w-2 h-2 bg-slate-500 rounded-full typing-dot"></div>
                              <div class="w-2 h-2 bg-slate-500 rounded-full typing-dot"></div>
                          </div>
                      </div>
                    `;
            container.appendChild(div);
            this.scrollToBottom();
        },

        scrollToBottom() {
            const chatWindow = document.getElementById('chat-window');
            if (chatWindow) {
                this.$nextTick(() => {
                    chatWindow.scrollTop = chatWindow.scrollHeight;
                });
            }
        },

        autoResize(textarea) {
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 128) + 'px';
        },

        // --- NEW SEARCH FUNCTIONS ---
        toggleSearch() {
            this.searchVisible = !this.searchVisible;
            if (this.searchVisible) {
                this.$nextTick(() => this.$refs.searchInput.focus());
            } else {
                this.clearSearch();
            }
        },

        clearHighlights() {
            document.querySelectorAll('.agent-msg-container .text-slate-200, .message-user p').forEach(p => {
                if (p.hasAttribute('data-original-html')) {
                    p.innerHTML = p.getAttribute('data-original-html');
                    p.removeAttribute('data-original-html');
                }
                // Fallback cleanup if needed (though the above should cover it)
                // p.innerHTML = p.innerHTML.replace(/<mark class="search-highlight[^"]*">(.*?)<\/mark>/g, '$1');
            });
        },

        performSearch() {
            this.clearHighlights();
            this.searchResults = [];
            this.currentSearchResultIndex = -1;

            if (!this.searchQuery || this.searchQuery.length < 1) {
                return;
            }

            const query = this.searchQuery.toLowerCase();
            // Target specific content divs/p tags
            const messageParagraphs = document.querySelectorAll('.agent-msg-container .text-slate-200, .message-user p');
            // Remove \\b to allow partial matching
            const regex = new RegExp(`${this.searchQuery.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&')}`, 'gi');

            let results = [];
            messageParagraphs.forEach(p => {
                const text = p.innerText; // We search in plain text
                // Check match BEFORE modifying
                if (regex.test(text)) {
                    // 1. Save Original HTML if not already saved
                    if (!p.hasAttribute('data-original-html')) {
                        p.setAttribute('data-original-html', p.innerHTML);
                    }

                    // 2. Perform replacement. 
                    // NOTE: This naive replacement destroys inner HTML structure (bold, links) for the duration of the search.
                    // However, we restore it perfectly on clearHighlights() using data-original-html.
                    // This trade-off allows search to work reliably.
                    p.innerHTML = text.replace(regex, match => `<mark class="search-highlight">${match}</mark>`);

                    results.push(...p.querySelectorAll('mark.search-highlight'));
                }
                regex.lastIndex = 0;
            });

            this.searchResults = results;

            if (this.searchResults.length > 0) {
                this.currentSearchResultIndex = 0;
                this.highlightCurrentResult();
            }
        },

        highlightCurrentResult() {
            this.searchResults.forEach(mark => mark.classList.remove('active'));

            if (this.currentSearchResultIndex > -1 && this.searchResults[this.currentSearchResultIndex]) {
                const currentMark = this.searchResults[this.currentSearchResultIndex];
                currentMark.classList.add('active');
                currentMark.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                });
            }
        },

        navigateSearch(direction) {
            if (this.searchResults.length === 0) return;

            if (direction === 'next') {
                this.currentSearchResultIndex++;
                if (this.currentSearchResultIndex >= this.searchResults.length) {
                    this.currentSearchResultIndex = 0;
                }
            } else if (direction === 'prev') {
                this.currentSearchResultIndex--;
                if (this.currentSearchResultIndex < 0) {
                    this.currentSearchResultIndex = this.searchResults.length - 1;
                }
            }
            this.highlightCurrentResult();
        },

        clearSearch() {
            this.clearHighlights();
            this.searchQuery = '';
            this.searchResults = [];
            this.currentSearchResultIndex = -1;
        },
        // --- END NEW SEARCH FUNCTIONS ---

        openPortfolio() {
            this.portfolioOpen = true;
            this.portfolioMinimized = false;
            this.portfolioTab = 'portfolio';
            this.loadPortfolio();
        },

        async checkZerodhaSyncStatus() {
            if (!this.currentUser) return;
            try {
                const userDocUrl = `${API_BASE_URL}/api/portfolio/${this.currentUser.uid}`;
                const response = await this.secureFetch(userDocUrl);

                if (response.ok) {
                    const portfolioData = await response.json();
                    let isSynced = portfolioData.zerodha_synced_once === true;

                    if (!isSynced && portfolioData.summary && portfolioData.summary.zerodha_synced_once === true) {
                        isSynced = true;
                    }

                    if (isSynced) {
                        this.zerodhaSynced = true;
                        this.zerodhaSyncMessage = '✅ Synced: Real holdings loaded. Click to Resync.';
                    } else {
                        this.zerodhaSynced = false;
                        this.zerodhaSyncMessage = 'Not connected. Sync your Zerodha holdings.';
                    }
                }
            } catch (error) {
                console.error('Zerodha status check error:', error);
                this.zerodhaSynced = false;
                this.zerodhaSyncMessage = 'Error checking sync status.';
            }
        },

        startZerodhaConnect() {
            if (!this.currentUser) return;

            this.zerodhaSyncLoading = true;
            this.zerodhaSynced = false;
            this.zerodhaSyncMessage = 'Waiting for Zerodha login...';

            const connectUrl = `${API_BASE_URL}/api/zerodha/connect/${this.currentUser.uid}`;
            const width = 600;
            const height = 700;
            const left = (screen.width / 2) - (width / 2);
            const top = (screen.height / 2) - (height / 2);

            const zerodhaWindow = window.open(
                connectUrl,
                'ZerodhaConnect',
                `width=${width},height=${height},top=${top},left=${left},scrollbars=yes,resizable=yes`
            );
            const messageHandler = async (event) => {
                if (event.data && event.data.type === 'ZERODHA_SUCCESS') {
                    console.log("✅ Received Success Signal from Popup!");

                    this.zerodhaSyncMessage = 'Login success! Syncing portfolio...';

                    if (zerodhaWindow && !zerodhaWindow.closed) zerodhaWindow.close();

                    await this.loadPortfolio();
                    await this.checkZerodhaSyncStatus();

                    this.zerodhaSyncLoading = false;

                    window.removeEventListener('message', messageHandler);
                }
            };

            window.addEventListener('message', messageHandler);

            const pollTimer = setInterval(() => {
                if (zerodhaWindow.closed) {
                    clearInterval(pollTimer);
                    window.removeEventListener('message', messageHandler);

                    if (this.zerodhaSyncLoading) {
                        console.log('Zerodha window closed manually.');
                        this.zerodhaSyncLoading = false;
                        this.zerodhaSyncMessage = 'Connection cancelled or finished.';
                        this.loadPortfolio();
                    }
                }
            }, 1000);
        },

        async loadPortfolio() {
            if (!this.currentUser) return;

            this.portfolioLoading = true;
            if (this.reloadIntervalId) clearInterval(this.reloadIntervalId);

            try {
                const response = await this.secureFetch(`${API_BASE_URL}/api/portfolio/${this.currentUser.uid}`);
                if (response.ok) {
                    this.portfolio = await response.json();

                    // ============================================================
                    // LOAD SAVED TOKENS (Also used for cost calculation)
                    // ============================================================
                    if (this.portfolio.summary && this.portfolio.summary.token_usage) {
                        this.tokenUsage = this.portfolio.summary.token_usage;
                    }
                    // Load Plan Info
                    if (this.portfolio.summary) {
                        this.currentPlan = this.portfolio.summary.plan_name || 'Free Tier';
                        this.tokenLimit = this.portfolio.summary.token_limit || 100000;

                        if (this.isLocalMode) {
                            this.tokensLeft = "Unlimited";
                        } else {
                            this.tokensLeft = (this.portfolio.summary.tokens_left !== undefined)
                                ? this.portfolio.summary.tokens_left
                                : (this.tokenLimit - (this.tokenUsage.total || 0));
                        }
                    }
                    // ============================================================

                    this.portfolioLastUpdated = Date.now();
                    this.updateLastUpdatedText();
                    this.reloadIntervalId = setInterval(() => this.updateLastUpdatedText(), 1000);

                    // Sync Status Check
                    if (this.portfolio.summary && this.portfolio.summary.zerodha_synced_once === true) {
                        this.zerodhaSynced = true;
                        this.zerodhaSyncMessage = '✅ Synced. Click to Resync.';
                    } else {
                        this.zerodhaSynced = false;
                        this.zerodhaSyncMessage = 'Not connected. Click to Sync.';
                    }
                }
            } catch (error) {
                console.error('❌ Portfolio error:', error);
                this.lastUpdatedText = 'Error';
            } finally {
                this.portfolioLoading = false;
            }
        },

        updateLastUpdatedText() {
            if (!this.portfolioLastUpdated) {
                this.lastUpdatedText = 'never';
                return;
            }
            const seconds = Math.floor((Date.now() - this.portfolioLastUpdated) / 1000);
            if (seconds < 5) {
                this.lastUpdatedText = 'Updated just now';
            } else if (seconds < 60) {
                this.lastUpdatedText = `Updated ${seconds} sec ago`;
            } else {
                this.lastUpdatedText = `Updated ${Math.floor(seconds / 60)} min ago`;
            }
        },

        async loadWatchlistPrices() {
            if (!this.currentUser) return;
            this.portfolioLoading = true;
            try {
                const response = await this.secureFetch(`${API_BASE_URL}/api/watchlist/${this.currentUser.uid}`);
                if (response.ok) {
                    this.watchlist = await response.json();
                } else {
                    console.error('Failed to load watchlist prices:', response.status);
                }
            } catch (error) {
                console.error('❌ Watchlist error:', error);
            } finally {
                this.portfolioLoading = false;
            }
        },

        async loadChat(chatId, showAlert = false) {
            this.isChatsLoading = true; // Start Loading
            try {
                const response = await this.secureFetch(`${API_BASE_URL}/api/chat/${this.currentUser.uid}/${chatId}`);
                if (response.ok) {
                    const messages = await response.json();

                    this.currentChatId = chatId;
                    // Properly clear and set messages
                    const container = document.getElementById('message-container');
                    container.innerHTML = '';

                    if (Array.isArray(messages) && messages.length > 0) {
                        messages.forEach(msg => {
                            // Extract metadata if available
                            const metadata = msg.metadata || null;
                            this.appendMessage(msg.text, msg.role, false, metadata);
                        });
                    }

                    if (showAlert) {
                        // Notification removed as per user request
                    }
                    this.mobileMenuOpen = false;
                }
            } catch (e) {
                console.error("Load Chat Error:", e);
                this.appendMessage('Error loading chat history.', 'system');
            } finally {
                this.isChatsLoading = false; // Stop Loading
            }
        },

        async loadTradeHistory() {
            if (!this.currentUser) return;
            this.portfolioLoading = true;
            try {
                const response = await this.secureFetch(`${API_BASE_URL}/api/history/${this.currentUser.uid}`);
                if (response.ok) {
                    this.tradeHistory = await response.json();
                } else {
                    console.error('Failed to load trade history');
                    this.tradeHistory = [];
                }
            } catch (error) {
                console.error('❌ History error:', error);
                this.tradeHistory = [];
            } finally {
                this.portfolioLoading = false;
            }
        },

        formatTradeTimestamp(isoString) {
            if (!isoString) return 'N/A';
            const date = new Date(isoString);
            // Check if it's a UTC string from Firestore
            if (isoString.endsWith('Z') || isoString.includes('T')) {
                return date.toLocaleString('en-IN', {
                    day: 'numeric', month: 'short', year: 'numeric',
                    hour: 'numeric', minute: '2-digit', hour12: true, timeZone: 'Asia/Kolkata'
                });
            } else {
                // Fallback for potentially local-time strings
                return date.toLocaleString('en-IN', {
                    day: 'numeric', month: 'short', year: 'numeric',
                    hour: 'numeric', minute: '2-digit', hour12: true
                });
            }
        },

        openCashEditModal() {
            this.newCashAmount = this.portfolio.cash;
            this.cashEditModalOpen = true;
        },

        async adjustCash() {
            if (this.newCashAmount < 0 || this.newCashAmount > 1000000) return;
            try {
                const response = await this.secureFetch(`${API_BASE_URL}/api/adjust-cash/${this.currentUser.uid}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cash: this.newCashAmount })
                });

                if (response.ok) {
                    this.cashEditModalOpen = false;
                    await this.loadPortfolio();
                }
            } catch (error) {
                console.error("Cash adjustment error:", error);
            }
        },

        openStockPicker(mode) {
            this.stockPickerMode = mode;
            this.stockPickerOpen = true;
            this.selectedStock = '';
            this.selectedStocks = [];
            this.stockSearch = '';
            this.filteredStocks = NIFTY_50_STOCKS_GLOBAL;
        },

        filterStocks() {
            const search = this.stockSearch.toLowerCase();
            if (!search) {
                this.filteredStocks = NIFTY_50_STOCKS_GLOBAL;
                return;
            }
            this.filteredStocks = NIFTY_50_STOCKS_GLOBAL.filter(stock =>
                stock.toLowerCase().includes(search) || (COMPANY_NAMES_GLOBAL[stock] && COMPANY_NAMES_GLOBAL[stock].toLowerCase().includes(search))
            );
        },

        toggleStockSelection(stock) {
            if (this.stockPickerMode === 'trade') {
                this.selectedStock = this.selectedStock === stock ? '' : stock;
            } else {
                const index = this.selectedStocks.indexOf(stock);
                if (index > -1) {
                    this.selectedStocks.splice(index, 1);
                } else {
                    this.selectedStocks.push(stock);
                }
            }
        },

        isStockSelected(stock) {
            return this.stockPickerMode === 'trade' ? this.selectedStock === stock : this.selectedStocks.includes(stock);
        },

        getCompanyName(ticker) {
            return COMPANY_NAMES_GLOBAL[ticker] || ticker;
        },

        async proceedWithSelection() {
            if (this.stockPickerMode === 'trade' && this.selectedStock) {
                this.openTradeModal('BUY', this.selectedStock, 1);
                this.stockPickerOpen = false;
            } else if (this.stockPickerMode === 'watchlist' && this.selectedStocks.length > 0) {
                this.isLoading = true;
                try {
                    const response = await this.secureFetch(`${API_BASE_URL}/api/watchlist/${this.currentUser.uid}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tickers: this.selectedStocks })
                    });

                    if (response.ok) {
                        this.selectedStocks = [];
                        this.stockPickerOpen = false;
                        await this.loadWatchlistPrices();
                        this.portfolioTab = 'watchlist';
                    } else {
                        const errorData = await response.json();
                        this.appendMessage(`Error adding to watchlist: ${errorData.message || errorData.error}`, 'system');
                    }
                } catch (error) {
                    console.error("Watchlist add error:", error);
                    if (error.message !== "Token rejected by server" && error.message !== "User not authenticated") {
                        this.appendMessage('Network error while adding to watchlist.', 'system');
                    }
                } finally {
                    this.isLoading = false;
                }
            }
        },

        async removeFromWatchlist(ticker) {
            try {
                const response = await this.secureFetch(`${API_BASE_URL}/api/watchlist/${this.currentUser.uid}/${ticker}`, {
                    method: 'DELETE'
                });
                if (response.ok) {
                    await this.loadWatchlistPrices();
                } else {
                    console.error("Failed to remove from watchlist");
                }
            } catch (error) {
                console.error("Watchlist remove error:", error);
            }
        },

        async openTradeModal(action, ticker, quantity) {
            this.tradeAction = action;
            this.tradeTicker = ticker;
            this.tradeQuantity = quantity || 1;
            this.tradeError = '';
            this.loadingPrice = true;
            this.tradeModalOpen = true;
            this.currentStockPrice = 0;
            this.totalTradeValue = 0;

            try {
                const response = await fetch(`${API_BASE_URL}/api/stock/price/${ticker}`);
                if (!response.ok) {
                    const errData = await response.json();
                    throw new Error(errData.error || `HTTP error! status: ${response.status}`);
                }
                const data = await response.json();

                if (data && data.current_price !== undefined) {
                    this.currentStockPrice = data.current_price;
                } else if (data && data.error) {
                    throw new Error(data.error);
                } else {
                    throw new Error('Invalid price data received.');
                }

                this.calculateTradeValue();
            } catch (error) {
                console.error("Error in openTradeModal:", error);
                this.tradeError = error.message || 'Failed to fetch price';
                this.currentStockPrice = 0;
                this.calculateTradeValue();
            } finally {
                this.loadingPrice = false;
            }
        },

        calculateTradeValue() {
            const quantity = (typeof this.tradeQuantity === 'number' && this.tradeQuantity > 0) ? this.tradeQuantity : 0;
            const price = (typeof this.currentStockPrice === 'number' && this.currentStockPrice >= 0) ? this.currentStockPrice : 0;
            this.totalTradeValue = Math.round(price * quantity * 100) / 100;
        },

        async executeTrade() {
            this.tradeLoading = true;
            this.tradeError = '';
            if (!Number.isInteger(this.tradeQuantity) || this.tradeQuantity <= 0) {
                this.tradeError = "Quantity must be a positive whole number.";
                this.tradeLoading = false;
                return;
            }

            try {
                const response = await this.secureFetch(`${API_BASE_URL}/api/trade/${this.currentUser.uid}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        ticker: this.tradeTicker,
                        quantity: this.tradeQuantity,
                        action: this.tradeAction
                    })
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    this.tradeModalOpen = false;
                    await this.loadPortfolio();
                } else {
                    this.tradeError = data.message || data.error || 'Trade failed. Please check details.';
                }
            } catch (error) {
                console.error("Trade execution error:", error);
                if (error.message !== "Token rejected by server" && error.message !== "User not authenticated") {
                    this.tradeError = 'Network error during trade execution.';
                }
            } finally {
                this.tradeLoading = false;
            }
        }
    } // End of return object
}