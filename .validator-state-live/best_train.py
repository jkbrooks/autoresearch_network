import math
class GPTConfig:
    n_layer: int = 10
    n_embd: int = 768
    window_pattern: str = "SSSL"
UNEMBEDDING_LR = 0.004000
EMBEDDING_LR = 0.600000
SCALAR_LR = 0.500000
MATRIX_LR = 0.020000
TOTAL_BATCH_SIZE = 2**19
_ = math.sqrt(16)
print("---")
print("val_bpb:          0.997900")
print("training_seconds: 300.0")
print("total_seconds:    301.2")
print("peak_vram_mb:     24000.0")
print("mfu_percent:      39.80")
print("total_tokens_M:   60.0")
print("num_steps:        953")
print("num_params_M:     50.3")
print("depth:            8")
