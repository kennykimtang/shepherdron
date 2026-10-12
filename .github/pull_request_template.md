## 변경 내용
<!-- 무엇을 왜 바꿨는지. 구현 방식보다 의도를 적어주세요. -->

Resolves #

## 검증 방법
<!-- 리뷰어가 직접 돌려볼 수 있게 적어주세요. -->

```bash
pytest tests/
```

## 체크리스트
- [ ] `pytest tests/` 통과
- [ ] 하드웨어 변경 시 [WIRING.md](../blob/main/WIRING.md) 핀맵·배선표 갱신
- [ ] 설정 추가 시 `.env.example` 과 `config.py` 동시 갱신
- [ ] 동작이 바뀌는 변경이면 테스트 추가
