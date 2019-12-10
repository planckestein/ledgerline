def create_customers(api, clock, count):
    ids = []
    for index in range(count):
        ids.append(api.post("/v1/customers", json={"name": "c%d" % index}).get_json()["id"])
        clock.advance(seconds=1)
    return ids


class TestPagination:
    def test_newest_first_with_cursor(self, api, clock):
        ids = create_customers(api, clock, 5)
        page = api.get("/v1/customers", limit=2).get_json()
        assert [c["id"] for c in page["data"]] == [ids[4], ids[3]]
        assert page["has_more"] is True
        assert page["url"] == "/v1/customers"

        page = api.get("/v1/customers", limit=2, starting_after=ids[3]).get_json()
        assert [c["id"] for c in page["data"]] == [ids[2], ids[1]]
        assert page["has_more"] is True

        page = api.get("/v1/customers", limit=2, starting_after=ids[1]).get_json()
        assert [c["id"] for c in page["data"]] == [ids[0]]
        assert page["has_more"] is False

    def test_ending_before(self, api, clock):
        ids = create_customers(api, clock, 5)
        page = api.get("/v1/customers", limit=2, ending_before=ids[1]).get_json()
        assert [c["id"] for c in page["data"]] == [ids[3], ids[2]]

    def test_default_limit(self, api, clock):
        create_customers(api, clock, 12)
        assert len(api.get("/v1/customers").get_json()["data"]) == 10

    def test_limit_validation(self, api):
        for value in ("0", "101", "ten"):
            response = api.get("/v1/customers", limit=value)
            assert response.status_code == 400
            assert response.get_json()["error"]["param"] == "limit"

    def test_unknown_cursor(self, api):
        response = api.get("/v1/customers", starting_after="cus_missing")
        assert response.status_code == 400
        assert response.get_json()["error"]["param"] == "starting_after"

    def test_cursor_of_other_tenant_is_unknown(self, api, other_api, clock):
        [mine] = create_customers(api, clock, 1)
        response = other_api.get("/v1/customers", starting_after=mine)
        assert response.status_code == 400

    def test_both_cursors(self, api, clock):
        ids = create_customers(api, clock, 2)
        response = api.get("/v1/customers", starting_after=ids[0], ending_before=ids[1])
        assert response.status_code == 400
