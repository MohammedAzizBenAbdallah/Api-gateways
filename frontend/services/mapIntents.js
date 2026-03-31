export default function mapIntents(intents) {
  const mappedIntents = intents.map((intent) => ({
    value: intent.intent_name,
    label: intent.intent_name,
  }));
  return mappedIntents;
}
