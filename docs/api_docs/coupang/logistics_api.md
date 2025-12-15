# 쿠팡 물류센터 API 문서

> **API 적용 가능한 구매자 사용자 지역**: 한국

---

## 1. 출고지 생성

상품 출고지를 생성합니다. 동일한 주소지/명칭의 출고지 중복 생성은 제한됩니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `POST` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v5/vendors/{vendorId}/outboundShippingCenters` |
| **Example URL** | `https://api-gateway.coupang.com/v2/providers/openapi/apis/api/v5/vendors/A00012345/outboundShippingCenters` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |

### 요청 파라미터 (Body)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `userId` | String | ✓ | 사용자 아이디 (WING 로그인 계정) |
| `shippingPlaceName` | String | ✓ | 출고지 이름 (최대 50자, 중복 불가) |
| `usable` | Boolean | - | 사용가능여부 (기본값 true) |
| `global` | Boolean | - | 국내(false)/해외(true) (기본값 false) |
| `placeAddresses` | Array | ✓ | 출고지 주소 |
| `placeAddresses.addressType` | String | ✓ | 주소 타입 (JIBUN, ROADNAME, OVERSEA) |
| `placeAddresses.countryCode` | String | ✓ | 국가 코드 (국내 KR) |
| `placeAddresses.companyContactNumber` | String | ✓ | 전화번호 (2~4-3~4-4 형식) |
| `placeAddresses.phoneNumber2` | String | - | 보조 전화번호 |
| `placeAddresses.returnZipCode` | String | ✓ | 우편번호 (5~6자리 숫자) |
| `placeAddresses.returnAddress` | String | ✓ | 주소 (최대 150자) |
| `placeAddresses.returnAddressDetail` | String | ✓ | 상세주소 (최대 200자) |
| `remoteInfos` | Array | - | 도서산간 추가배송비 |
| `remoteInfos.deliveryCode` | String | ✓ | 택배사 코드 |
| `remoteInfos.jeju` | Number | ✓ | 제주 지역 배송비 (0원 또는 1000~8000원) |
| `remoteInfos.notJeju` | Number | ✓ | 제주 외 지역 배송비 |

### 요청 예시

```json
{
  "vendorId": "A00011620",
  "userId": "testId",
  "shippingPlaceName": "상품출고지 생성",
  "global": "false",
  "usable": "true",
  "placeAddresses": [
    {
      "addressType": "JIBUN",
      "countryCode": "KR",
      "companyContactNumber": "02-15**-1234",
      "phoneNumber2": "010-12**-**78",
      "returnZipCode": "10516",
      "returnAddress": "경기도 파주시 탄현면 월롱산로",
      "returnAddressDetail": "294-58"
    }
  ],
  "remoteInfos": [
    {
      "deliveryCode": "KGB",
      "jeju": "5000",
      "notJeju": "2500"
    }
  ]
}
```

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `code` | Number | 서버 응답 코드 |
| `message` | String | 서버 응답 메시지 |
| `data.resultCode` | String | 결과 코드 (SUCCESS or FAIL) |
| `data.resultMessage` | String | 결과 메시지 (출고지 코드) |

### 응답 예시

```json
{
  "code": "200",
  "message": "SUCCESS",
  "data": {
    "resultCode": "SUCCESS",
    "resultMessage": "115"
  }
}
```

---

## 2. 출고지 조회

등록된 출고지 목록 또는 특정 조건(출고지명, 출고지 코드)에 맞는 출고지 정보를 조회합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/marketplace_openapi/apis/api/v2/vendor/shipping-place/outbound` |
| **Example URL** | `https://api-gateway.coupang.com/v2/providers/marketplace_openapi/apis/api/v2/vendor/shipping-place/outbound?pageSize=50&pageNum=1` |

### 요청 파라미터 (Query String)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `placeCodes` | Long | - | 출고지 코드 |
| `placeNames` | String | - | 출고지명 |
| `pageNum` | Integer | - | 조회 페이지 (목록 조회 시 필수, Min=1) |
| `pageSize` | Integer | - | 페이지당 최대 호출 수 (Default=10, Max=50) |

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `content` | Array | 출고지 목록 데이터 |
| `content.outboundShippingPlaceCode` | Long | 출고지 코드 |
| `content.shippingPlaceName` | String | 출고지 이름 |
| `content.placeAddresses` | Array | 출고지 주소 |
| `content.remoteInfos` | Array | 도서산간 배송정보 |
| `content.createDate` | Object | 생성일 (YYYY/MM/DD) |
| `content.usable` | Boolean | 사용가능 여부 |
| `pagination` | Object | 페이징 정보 |

### 응답 예시

```json
{
  "content": [
    {
      "outboundShippingPlaceCode": 1111222,
      "shippingPlaceName": "상품출고지1",
      "createDate": "2019/06/24",
      "placeAddresses": [
        {
          "addressType": "JIBUN",
          "countryCode": "KR",
          "companyContactNumber": "02-1234-5678",
          "returnZipCode": "05510",
          "returnAddress": "서울특별시 송파구 신천동",
          "returnAddressDetail": "7-30, Tower출고지"
        }
      ],
      "remoteInfos": [
        {
          "remoteInfoId": 581487,
          "deliveryCode": "DIRECT",
          "jeju": 5000,
          "notJeju": 2500,
          "usable": true
        }
      ],
      "usable": true
    }
  ],
  "pagination": {
    "currentPage": 1,
    "countPerPage": 1,
    "totalPages": 1,
    "totalElements": 1
  }
}
```

---

## 3. 출고지 수정

출고지를 수정합니다. `outboundShippingPlaceCode` 및 `remoteInfoId`가 필요하며, '출고지 조회' API를 통해 얻을 수 있습니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `PUT` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v5/vendors/{vendorId}/outboundShippingCenters/{outboundShippingPlaceCode}` |
| **Example URL** | `https://api-gateway.coupang.com/v2/providers/openapi/apis/api/v5/vendors/A00012345/outboundShippingCenters/123456` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `outboundShippingPlaceCode` | Number | ✓ | 수정하려는 출고지 코드 |

### 요청 파라미터 (Body)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `userId` | String | ✓ | 사용자 ID (WING 로그인 계정) |
| `outboundShippingPlaceCode` | Number | - | 출고지 코드 |
| `shippingPlaceName` | String | - | 출고지 이름 (최대 50자) |
| `usable` | Boolean | - | 사용 가능 여부 |
| `global` | Boolean | - | 국내(false)/해외(true) |
| `placeAddresses` | Array | ✓ | 출고지 주소 |
| `remoteInfos` | Array | - | 도서산간 추가배송비 |

### 응답 예시

```json
{
  "code": "200",
  "message": "SUCCESS",
  "data": {
    "resultCode": "SUCCESS",
    "resultMessage": "Modify successfully"
  }
}
```

---

## 4. 반품지 생성

반품지를 생성합니다. 택배사 계약 코드가 없을 경우 생성하지 않고 상품 등록 가능합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `POST` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v5/vendors/{vendorId}/returnShippingCenters` |
| **Example URL** | `https://api-gateway.coupang.com/v2/providers/openapi/apis/api/v5/vendors/A00012345/returnShippingCenters` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |

### 요청 파라미터 (Body)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `userId` | String | ✓ | 사용자 아이디 (WING 로그인 계정) |
| `shippingPlaceName` | String | ✓ | 반품지 이름 |
| `goodsflowInfoOpenApiDto` | Object | ✓ | 택배사 정보 |
| `goodsflowInfoOpenApiDto.deliverCode` | String | ✓ | 택배사 코드 |
| `goodsflowInfoOpenApiDto.deliverName` | String | ✓ | 택배사명 |
| `goodsflowInfoOpenApiDto.contractNumber` | String | ✓ | 택배사 계약코드 |
| `placeAddresses` | Array | ✓ | 반품지 주소 |

### 응답 예시

```json
{
  "code": "200",
  "message": "SUCCESS",
  "data": {
    "resultCode": "SUCCESS",
    "resultMessage": "반품지코드"
  }
}
```

---

## 5. 반품지 목록 조회

업체 코드를 통해 반품지를 조회합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v5/vendors/{vendorId}/returnShippingCenters` |
| **Example URL** | `https://api-gateway.coupang.com/v2/providers/openapi/apis/api/v5/vendors/A00012345/returnShippingCenters?pageNum=1&pageSize=50` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |

### 요청 파라미터 (Query String)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `pageNum` | Number | - | 페이지 수 (기본값 1) |
| `pageSize` | Number | - | 페이지당 건수 (기본값 10, 최대 50) |

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `vendorId` | String | 업체 코드 |
| `returnCenterCode` | String | 반품지 센터코드 |
| `shippingPlaceName` | String | 반품지 이름 |
| `deliverCode` | String | 택배사 코드 |
| `deliverName` | String | 택배사명 |
| `usable` | Boolean | 사용여부 |
| `placeAddresses` | Array | 반품지 주소 |

---

## 6. 반품지 수정

반품지를 수정합니다. `returnCenterCode`가 필요하며, [반품지 목록 조회] API를 통해 얻을 수 있습니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `PUT` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v5/vendors/{vendorId}/returnShippingCenters/{returnCenterCode}` |
| **Example URL** | `https://api-gateway.coupang.com/v2/providers/openapi/apis/api/v5/vendors/A00012345/returnShippingCenters/1100044653` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `returnCenterCode` | Number | ✓ | 반품지 코드 |

### 요청 파라미터 (Body)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `userId` | String | ✓ | 사용자 ID (WING 로그인 계정) |
| `returnCenterCode` | Number | ✓ | 반품지 코드 |
| `shippingPlaceName` | String | - | 반품지 이름 |
| `usable` | Boolean | - | 사용 가능 여부 |
| `placeAddresses` | Array | ✓ | 반품지 주소 |
| `goodsflowInfoDto` | Object | - | 굿스플로 택배 연동 정보 |

### 응답 예시

```json
{
  "code": "200",
  "message": "SUCCESS",
  "data": {
    "resultCode": "SUCCESS",
    "resultMessage": "Modify successfully"
  }
}
```

---

## 7. 반품지 단건 조회

반품지 센터코드(returnCenterCode)로 반품지 정보를 조회합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v3/return/shipping-places/center-code` |
| **Example URL** | `https://api-gateway.coupang.com/v2/providers/openapi/apis/api/v3/return/shipping-places/center-code?returnCenterCodes=1000000051,1000006047` |

### 요청 파라미터 (Query String)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `returnCenterCodes` | String | - | 반품지 센터코드 (쉼표로 구분, 최대 100개) |

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `vendorId` | String | 업체 코드 |
| `returnCenterCode` | String | 반품지 센터코드 |
| `shippingPlaceName` | String | 반품지 이름 |
| `deliverCode` | String | 택배사 코드 |
| `deliverName` | String | 택배사명 |
| `goodsflowStatus` | String | 굿스플로 상태 |
| `createdAt` | Number | 생성일 (Timestamp) |
| `usable` | Boolean | 사용여부 |
| `placeAddresses` | Array | 반품지 주소 |

---

## 8. 택배사 코드

출고지/반품지 설정에 사용되는 택배사 코드 목록입니다.

| 코드 | 택배사명 | 송장번호 자릿수 |
|------|----------|----------------|
| `HYUNDAI` | 롯데택배 | 10, 12, 13자리 |
| `KGB` | 로젠택배 | 10 또는 11자리 |
| `EPOST` | 우체국 | 13자리 |
| `HANJIN` | 한진택배 | 10 또는 12자리 |
| `CJGLS` | CJ대한통운 | 10 또는 12자리 |
| `KOREX` | 대한통운[합병] | 10 또는 12자리 |
| `KDEXP` | 경동택배 | 8~16자리 |
| `DIRECT` | 업체직송 | 숫자로만 입력, 트래킹 안됨 |
| `ILYANG` | 일양택배 | 8~16자리 |
| `CHUNIL` | 천일특송 | 11자리 |
| `AJOU` | 아주택배 | - |
| `CSLOGIS` | SC로지스 | - |
| `DAESIN` | 대신택배 | 13자리 |
| `CVS` | CVS택배 | 10, 12자리 |
