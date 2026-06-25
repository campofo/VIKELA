#ifndef VIKELA_CONFIG_EXAMPLE_H
#define VIKELA_CONFIG_EXAMPLE_H

// Copy this file to config.h and update the values for your SIM card,
// backend, user/device identity, and emergency contacts.

// Cellular APN settings from your SIM/network provider.
static const char CELLULAR_APN[] = "internet";
static const char CELLULAR_USER[] = "";
static const char CELLULAR_PASS[] = "";

// HTTP endpoint that receives panic alerts.
// This first firmware build supports plain HTTP URLs.
// Example: "http://example.com/api/alerts/hardware"
static const char BACKEND_ALERT_URL[] = "http://example.com/api/alerts/hardware";

// Device/user identity sent in HTTP payloads and SMS fallback messages.
static const char DEVICE_ID[] = "VIKELA-T-SIM7000G-001";
static const char USER_ID[] = "user-001";
static const char USER_DISPLAY_NAME[] = "VIKELA User";

// SMS fallback settings.
static const char SMS_MESSAGE_PREFIX[] = "VIKELA EMERGENCY ALERT";
static const char* const EMERGENCY_CONTACTS[] = {
  "+233000000000",
  "+233000000001"
};
static const int EMERGENCY_CONTACT_COUNT =
    sizeof(EMERGENCY_CONTACTS) / sizeof(EMERGENCY_CONTACTS[0]);

#endif
