// The palette now lives in lib/ so the seat map can use it without importing
// from the organizer feature. Re-exported so existing imports keep working.
export { MAX_TIERS, TIER_COLORS, tierColor } from '@/lib/tier-colors'
