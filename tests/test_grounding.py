import json

import pytest

from src.catalogue import Catalogue, retailer_url, validate_model_answer
from src.schemas import ModelAnswer, Preferences
from src.settings import Settings


@pytest.mark.parametrize(
    "url",
    [
        "https://sportsdirect.com.evil.test/a",
        "https://evil.test/sportsdirect.com",
        "https://sportsdirect.com@evil.test/",
        "https://evil.test/?q=sportsdirect.com",
        "http://sportsdirect.com/a",
        "javascript:alert(1)",
        "https://sportsdirect.com:444/a",
        "https://sportsdirect.com\\@evil.test/a",
        "https://sportsdirect.com%2eevil.test/a",
        "https://sportsdirect.com/\nattack",
        "https://user:password@sportsdirect.com/",
    ],
)
def test_retailer_spoofing_rejected(url):
    with pytest.raises(ValueError):
        retailer_url(url, ("sportsdirect.com",))


def test_real_hostname_canonicalized():
    assert (
        retailer_url("https://WWW.SPORTSDIRECT.COM:443/item#section", ("sportsdirect.com",))
        == "https://www.sportsdirect.com/item"
    )


def test_catalogue_total_budget_and_no_fake_links(config):
    catalogue = Catalogue(config.catalogue_path, config.allowed_retailers)
    products = catalogue.search("classic business outfit", Preferences(budget_gbp=50))
    assert products and sum(p.price_pence for p in products) <= 5000
    assert all(p.url is None for p in products)
    assert catalogue.search("unknownxyz", Preferences()) == []
    assert catalogue.search("business", Preferences(budget_gbp=0)) == []


def test_duplicate_ids_fail_startup(config, tmp_path):
    data = json.loads(config.catalogue_path.read_text())
    data["products"].append(data["products"][0])
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        Catalogue(path, config.allowed_retailers)


@pytest.mark.parametrize(
    "answer",
    [
        "Buy at https://evil.test",
        "Costs £4",
        "In stock now",
        "Guaranteed",
        "[click](javascript:alert(1))",
    ],
)
def test_generated_commerce_claims_rejected(answer):
    assert not validate_model_answer(answer, [])


async def test_no_provider_fake_success(app, client, image):
    result = (
        await client.post(
            "/api/chat", json={"message": "visualize a casual outfit", "image": image}
        )
    ).json()
    assert result["products"] and result["image"] is None
    assert result["image_kind"] == "schematic" and result["engine"] == "catalogue"
    assert any("No image analysis" in warning for warning in result["warnings"])
    assert any("not an AI-generated" in warning for warning in result["warnings"])
    assert not (await app.state.store.read(client.cookies.get("retail_session"))).wardrobe_context


@pytest.mark.parametrize(
    "bad",
    [
        ModelAnswer(answer="Try this", product_ids=["fabricated-id"]),
        ModelAnswer(answer="Costs £1", product_ids=[]),
    ],
)
async def test_model_cannot_inject_products_or_prices(app, client, bad):
    app.state.config.engine = "ollama"

    async def answer(messages):
        return bad, {}

    app.state.orchestrator.model.answer = answer
    result = (await client.post("/api/chat", json={"message": "classic business outfit"})).json()
    assert result["engine"] == "catalogue"
    assert result["products"] and "fabricated-id" not in [p["id"] for p in result["products"]]
    assert "£1" not in result["answer"] and result["warnings"]


async def test_prior_conversation_does_not_override_scope(client):
    for question in [
        "hi",
        "what do you do",
        "classic business outfit under £100",
        "cook a recipe while wearing this outfit",
    ]:
        response = await client.post("/api/chat", json={"message": question})
        assert response.status_code == 200
    assert response.json()["route"] == "out_of_scope"
    assert response.json()["products"] == []


async def test_invalid_image_does_not_persist_context(app, client):
    result = await client.post(
        "/api/chat", json={"message": "style this shirt", "image": "http://169.254.169.254/private"}
    )
    assert result.status_code == 422
    assert (await client.get("/api/history")).json()["history"] == []


def test_wildcard_origin_configuration_rejected():
    with pytest.raises(ValueError):
        Settings(_env_file=None, allowed_origins=("https://*.example.com",))


async def test_valid_model_text_is_never_a_source_of_commerce_facts(app, client):
    app.state.config.engine = "ollama"

    async def answer(messages):
        candidates = app.state.catalogue.search(
            "classic business outfit", Preferences(occasion="business", style="classic")
        )
        return ModelAnswer(
            answer="This fake shop sells magic trousers.", product_ids=[candidates[0].id]
        ), {}

    app.state.orchestrator.model.answer = answer
    result = (await client.post("/api/chat", json={"message": "classic business outfit"})).json()
    assert result["engine"] == "ollama"
    assert "fake shop" not in result["answer"] and "magic trousers" not in result["answer"]
    assert len(result["products"]) == 1


async def test_cheaper_followup_reduces_outfit_budget(client):
    await client.post("/api/chat", json={"message": "classic business outfit under £100"})
    result = (await client.post("/api/chat", json={"message": "something cheaper"})).json()
    assert result["preferences"]["budget_gbp"] == 80
    assert sum(p["price_pence"] for p in result["products"]) <= 8000
