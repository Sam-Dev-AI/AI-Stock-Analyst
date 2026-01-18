function authActionApp() {
    return {
        mode: 'loading', // resetPassword | verifyEmail | recoverEmail (unsupported)
        actionCode: '',

        // UI Strings
        pageTitle: 'Please wait...',
        pageDescription: 'Processing your request.',
        loadingText: 'Loading...',

        // State
        isLoading: true,
        isVerifying: false,
        isSubmitting: false,
        error: false,
        success: false,

        // Error/Success Content
        errorTitle: 'Error',
        errorMessage: 'Something went wrong.',
        successTitle: 'Success',
        successMessage: 'Action completed successfully.',

        // Form Data
        password: '',
        confirmPassword: '',
        formError: '',

        // Firebase
        fbAuth: null,
        fbApplyCode: null,
        fbConfirmReset: null,
        fbVerifyCode: null,

        async init() {
            console.log("Initializing Auth Action Handler...");

            // 1. Parse URL Params
            const urlParams = new URLSearchParams(window.location.search);
            this.mode = urlParams.get('mode');
            this.actionCode = urlParams.get('oobCode');

            console.log(`Mode: ${this.mode}, Code: ${this.actionCode ? 'Present' : 'Missing'}`);

            if (!this.actionCode) {
                this.handleError("Invalid Link", "No action code found. Please use the link from your email.");
                return;
            }

            // 2. Load Firebase
            try {
                let attempts = 0;
                while (!window.initAuthAction && attempts < 50) {
                    await new Promise(r => setTimeout(r, 100));
                    attempts++;
                }
                if (!window.initAuthAction) throw new Error("Firebase SDK failed to load.");

                const { auth, applyActionCode, confirmPasswordReset, verifyPasswordResetCode } = await window.initAuthAction();
                this.fbAuth = auth;
                this.fbApplyCode = applyActionCode;
                this.fbConfirmReset = confirmPasswordReset;
                this.fbVerifyCode = verifyPasswordResetCode;

            } catch (e) {
                this.handleError("System Error", "Failed to load authentication modules.");
                return;
            }


            // 3. Router

            if (this.mode === 'verifyEmail') {
                // Correct flow: Start verify immediately
                this.isVerifying = true;
                this.error = false;
                this.success = false;
                this.isLoading = false;

                this.pageTitle = 'Email Verification';
                this.pageDescription = 'Verifying your email address...';
                this.loadingText = 'Verifying...';
                await this.doVerifyEmail();
            }
            else if (this.mode === 'resetPassword') {
                this.isVerifying = true;
                this.error = false;
                this.isLoading = false;

                this.pageTitle = 'Reset Password';
                this.pageDescription = 'Create a new password for your account.';
                this.loadingText = 'Checking link validity...';
                await this.doCheckResetLink();
            } else {
                this.handleError("Unknown Action", "The link you followed is invalid or unsupported.");
            }
        },

        async doVerifyEmail() {
            try {
                await this.fbApplyCode(this.fbAuth, this.actionCode);
                this.successTitle = "Email Verified!";
                this.successMessage = "Your email has been successfully verified. You can now log in.";

                // Ensure mutual exclusivity
                this.success = true;
                this.error = false;
                this.isVerifying = false;

                // Clean URL
                window.history.replaceState({}, document.title, window.location.pathname);
            } catch (e) {
                // Specific check for already used link
                if (e.code === 'auth/invalid-action-code' || e.message.includes('invalid-action-code')) {
                    // If the code is invalid, it often means it was just consumed. 
                    // We show a "Success" state but with a different message to avoid confusion.

                    this.successTitle = "Email Verified";
                    this.successMessage = "This verification link has already been used. You are likely already verified. Please continue to log in.";
                    this.success = true;
                    this.error = false;
                    this.isVerifying = false;
                    window.history.replaceState({}, document.title, window.location.pathname);
                    return;
                }

                this.handleError("Verification Failed", e.message.replace('Firebase: ', ''));
            }
        },

        async doCheckResetLink() {
            try {
                const email = await this.fbVerifyCode(this.fbAuth, this.actionCode);
                console.log("Reset link valid for:", email);
                this.isVerifying = false; // Stop loading, show form
            } catch (e) {
                this.handleError("Link Expired", "This password reset link is invalid or has expired.");
            }
        },

        async handleReset() {
            if (this.password !== this.confirmPassword) {
                this.formError = "Passwords do not match.";
                return;
            }
            this.isSubmitting = true;
            try {
                await this.fbConfirmReset(this.fbAuth, this.actionCode, this.password);
                this.successTitle = "Password Changed";
                this.successMessage = "Your password has been updated. You can now log in.";
                this.success = true;
                window.history.replaceState({}, document.title, window.location.pathname);
            } catch (e) {
                this.formError = e.message.replace('Firebase: ', '');
                this.isSubmitting = false;
            }
        },

        handleError(title, msg) {
            this.isLoading = false;
            this.isVerifying = false;
            this.success = false; // Ensure success is cleared
            this.error = true;
            this.errorTitle = title;
            this.errorMessage = msg;
        }
    }
}
