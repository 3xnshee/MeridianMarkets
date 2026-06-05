(function () {
  if (window.MERIDIAN_PRIVATE_PROVIDER) return;

  const unavailable = async (action) => {
    throw new Error(`Private trading service is not configured. Cannot ${action}.`);
  };

  window.MERIDIAN_PRIVATE_PROVIDER = {
    name: 'public-noop-provider',
    connected: false,
    authorized: false,
    async getStatus() {
      return {
        connected: false,
        authorized: false,
        accountName: null,
        institution: null,
        reason: 'Private trading service is not configured.',
      };
    },
    async connect() {
      return { connected: false, authorized: false, message: 'No private trading service is configured.' };
    },
    async getAccountSummary() {
      return unavailable('load account summary');
    },
    async getWalletSummary() {
      return unavailable('load wallet summary');
    },
    async placeOrder() {
      return unavailable('place an order');
    },
    async listTransactions() {
      return unavailable('list transactions');
    },
  };
})();
