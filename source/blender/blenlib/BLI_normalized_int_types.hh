/* SPDX-FileCopyrightText: 2026 Blender Authors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#pragma once

/** \file
 * \ingroup bli
 */

#include "BLI_math_vector.hh"

namespace blender {

namespace detail {
template<typename T, int CompLen, int... CompBitCounts> struct NormalizedIntVec;

template<typename T, int SizeX, int SizeY> struct NormalizedIntVec<T, 2, SizeX, SizeY> {
  using VecT = VecBase<float, 2>;
  using IntVecT = VecBase<T, 2>;

  T x : SizeX;
  T y : SizeY;

  constexpr static bool is_signed = std::is_signed_v<T>;
  constexpr static T x_max = T((1u << (SizeX - int(is_signed))) - 1);
  constexpr static T y_max = T((1u << (SizeY - int(is_signed))) - 1);

  NormalizedIntVec() = default;
  constexpr NormalizedIntVec(IntVecT value) : x(value.x), y(value.y) {}

  operator IntVecT() const
  {
    return IntVecT(x, y);
  }

  static constexpr VecT max()
  {
    return VecT(x_max, y_max);
  }

  static constexpr VecT min()
  {
    if (is_signed) {
      return VecT(-x_max, -y_max);
    }
    return VecT(0.0f, 0.0f);
  }
};

template<typename T, int SizeX, int SizeY, int SizeZ, int SizeW>
struct NormalizedIntVec<T, 4, SizeX, SizeY, SizeZ, SizeW> {
  using VecT = VecBase<float, 4>;
  using IntVecT = VecBase<T, 4>;

  T x : SizeX;
  T y : SizeY;
  T z : SizeZ;
  T w : SizeW;

  constexpr static bool is_signed = std::is_signed_v<T>;
  constexpr static T x_max = T((1u << (SizeX - int(is_signed))) - 1);
  constexpr static T y_max = T((1u << (SizeY - int(is_signed))) - 1);
  constexpr static T z_max = T((1u << (SizeZ - int(is_signed))) - 1);
  constexpr static T w_max = T((1u << (SizeW - int(is_signed))) - 1);

  NormalizedIntVec() = default;
  constexpr NormalizedIntVec(IntVecT value) : x(value.x), y(value.y), z(value.z), w(value.w) {}

  operator IntVecT() const
  {
    return IntVecT(x, y, z, w);
  }

  static constexpr VecT max()
  {
    return VecT(x_max, y_max, z_max, w_max);
  }

  static constexpr VecT min()
  {
    if constexpr (is_signed) {
      return VecT(-x_max, -y_max, -z_max, -w_max);
    }
    return VecT(0.0f, 0.0f, 0.0f, 0.0f);
  }
};

template<>
struct NormalizedIntVec<int32_t, 4, 10, 10, 10, 2> {
  using VecT = VecBase<float, 4>;
  using IntVecT = VecBase<int32_t, 4>;

  int32_t x : 10;
  int32_t y : 10;
  int32_t z : 10;
  int32_t w : 2;

  constexpr static bool is_signed = true;
  constexpr static int32_t x_max = 511;
  constexpr static int32_t y_max = 511;
  constexpr static int32_t z_max = 511;
  constexpr static int32_t w_max = 1;

  NormalizedIntVec() = default;
  constexpr NormalizedIntVec(IntVecT value) : x(value.x), y(value.y), z(value.z), w(value.w) {}

  operator IntVecT() const
  {
    return IntVecT(x, y, z, w);
  }

  static constexpr VecT max()
  {
    return VecT(511.0f, 511.0f, 511.0f, 1.0f);
  }

  static constexpr VecT min()
  {
    return VecT(-511.0f, -511.0f, -511.0f, -1.0f);
  }
};

template<>
struct NormalizedIntVec<uint32_t, 4, 10, 10, 10, 2> {
  using VecT = VecBase<float, 4>;
  using IntVecT = VecBase<uint32_t, 4>;

  uint32_t x : 10;
  uint32_t y : 10;
  uint32_t z : 10;
  uint32_t w : 2;

  constexpr static bool is_signed = false;
  constexpr static uint32_t x_max = 1023;
  constexpr static uint32_t y_max = 1023;
  constexpr static uint32_t z_max = 1023;
  constexpr static uint32_t w_max = 3;

  NormalizedIntVec() = default;
  constexpr NormalizedIntVec(IntVecT value) : x(value.x), y(value.y), z(value.z), w(value.w) {}

  operator IntVecT() const
  {
    return IntVecT(x, y, z, w);
  }

  static constexpr VecT max()
  {
    return VecT(1023.0f, 1023.0f, 1023.0f, 3.0f);
  }

  static constexpr VecT min()
  {
    return VecT(0.0f, 0.0f, 0.0f, 0.0f);
  }
};

}  // namespace detail

template<typename T, int CompLen, int... CompBitCounts>
  requires(std::is_same_v<T, int32_t> || std::is_same_v<T, uint32_t>)
struct NormalizedIntVecBase : detail::NormalizedIntVec<T, CompLen, CompBitCounts...> {
  using IntPacked = detail::NormalizedIntVec<T, CompLen, CompBitCounts...>;
  using typename IntPacked::IntVecT;
  using typename IntPacked::VecT;

  NormalizedIntVecBase() = default;

  NormalizedIntVecBase(IntVecT value) : IntPacked(value) {}

  /* Adding rounding would be the standard compliant conversion.
   * But this would introduce perf regression. */
  NormalizedIntVecBase(VecT val)
      : IntPacked(IntVecT(math::clamp(val * IntPacked::max(), IntPacked::min(), IntPacked::max())))
  {
  }

  operator VecT() const
  {
    return VecT(IntVecT(*this)) / IntPacked::max();
  }
};

using char4_norm = NormalizedIntVecBase<int32_t, 4, 8, 8, 8, 8>;
using uchar4_norm = NormalizedIntVecBase<uint32_t, 4, 8, 8, 8, 8>;
using short2_norm = NormalizedIntVecBase<int32_t, 2, 16, 16>;
using ushort2_norm = NormalizedIntVecBase<uint32_t, 2, 16, 16>;
using short4_norm = NormalizedIntVecBase<int32_t, 4, 16, 16, 16, 16>;
using ushort4_norm = NormalizedIntVecBase<uint32_t, 4, 16, 16, 16, 16>;
using int1010102_norm = NormalizedIntVecBase<int32_t, 4, 10, 10, 10, 2>;
using uint1010102_norm = NormalizedIntVecBase<uint32_t, 4, 10, 10, 10, 2>;

}  // namespace blender
