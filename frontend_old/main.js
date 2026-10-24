
const pages = ["dashboard", "medicines", "add"];
let medicines = [];
let editingId = null;

function showPage(name) {
    pages.forEach(page => {
        document.getElementById(`${page}-page`)
            .classList.toggle("hidden", page !== name);
    });

    document.getElementById("page-title").textContent = {
        dashboard: "Dashboard",
        medicines: "Medicine Inventory",
        add: editingId === null ? "Add Medicine" : "Edit Medicine"
    }[name];

    document.querySelectorAll(".nav-item").forEach(button => {
        button.classList.toggle("active", button.dataset.page === name);
    });

    if (name === "medicines") renderMedicines();
}

document.querySelectorAll("[data-page]").forEach(button => {
    button.addEventListener("click", () => showPage(button.dataset.page));
});

document.querySelectorAll("[data-go]").forEach(button => {
    button.addEventListener("click", () => {
        editingId = null;
        document.getElementById("medicine-form").reset();
        document.getElementById("form-title").textContent = "Add New Medicine";
        showPage(button.dataset.go);
    });
});

function renderMedicines() {
    const query = document.getElementById("search").value.toLowerCase();

    const filtered = medicines.filter(medicine =>
        `${medicine.name} ${medicine.category}`.toLowerCase().includes(query)
    );

    const rows = filtered.map(medicine => `
        <tr>
            <td>${escapeHTML(medicine.name)}</td>
            <td>${escapeHTML(medicine.category)}</td>
            <td>${medicine.quantity}</td>
            <td>₱${Number(medicine.unit_price).toFixed(2)}</td>
            <td>
                <button class="secondary" data-edit="${medicine.id}">Edit</button>
                <button class="secondary" data-delete="${medicine.id}">Delete</button>
            </td>
        </tr>
    `).join("");

    document.getElementById("medicine-table").innerHTML =
        rows || '<tr><td colspan="5">No medicine records yet.</td></tr>';
}

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;",
        '"': "&quot;", "'": "&#39;"
    })[character]);
}

document.getElementById("search").addEventListener("input", renderMedicines);

document.getElementById("medicine-table").addEventListener("click", event => {
    const editId = event.target.dataset.edit;
    const deleteId = event.target.dataset.delete;

    if (editId) {
        const medicine = medicines.find(item => String(item.id) === editId);
        if (!medicine) return;

        editingId = medicine.id;
        const form = document.getElementById("medicine-form");

        Object.keys(medicine).forEach(key => {
            if (form.elements[key]) form.elements[key].value = medicine[key] ?? "";
        });

        document.getElementById("form-title").textContent = "Edit Medicine";
        showPage("add");
    }

    if (deleteId && confirm("Delete this medicine?")) {
        medicines = medicines.filter(item => String(item.id) !== deleteId);
        renderMedicines();
        updateDashboard();
    }
});

document.getElementById("medicine-form").addEventListener("submit", event => {
    event.preventDefault();

    const formData = new FormData(event.target);
    const medicine = Object.fromEntries(formData.entries());
    medicine.quantity = Number(medicine.quantity);
    medicine.unit_price = Number(medicine.unit_price);

    if (editingId === null) {
        medicine.id = Date.now();
        medicines.push(medicine);
    } else {
        medicines = medicines.map(item =>
            item.id === editingId ? { ...medicine, id: editingId } : item
        );
    }

    updateDashboard();
    event.target.reset();
    editingId = null;
    showPage("medicines");
    document.getElementById("notice").textContent =
        "Saved in this page's temporary memory. Django API connection is not set up yet.";
});

function updateDashboard() {
    document.getElementById("total-medicines").textContent = medicines.length;
    document.getElementById("total-stock").textContent =
        medicines.reduce((sum, item) => sum + item.quantity, 0);
    document.getElementById("low-stock").textContent =
        medicines.filter(item => item.quantity < 10).length;

    document.getElementById("recent-table").innerHTML = medicines.slice(-5).reverse()
        .map(item => `<tr>
            <td>${escapeHTML(item.name)}</td>
            <td>${escapeHTML(item.category)}</td>
            <td>${item.quantity}</td>
            <td>₱${item.unit_price.toFixed(2)}</td>
        </tr>`).join("") ||
        '<tr><td colspan="4">No medicines added yet.</td></tr>';
}

showPage("dashboard");
updateDashboard();
