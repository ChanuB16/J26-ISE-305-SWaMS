class ClassifyResult {
  final String category;
  final double confidence;
  final bool reliable;
  final String tip;
  const ClassifyResult({
    required this.category,
    required this.confidence,
    required this.reliable,
    required this.tip,
  });
}
